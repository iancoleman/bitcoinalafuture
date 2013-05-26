from django.utils.timezone import utc
from django.db import IntegrityError
from django.db import transaction
from django.db.models import F

from thefuture.models import Bitcoin_Price
from thefuture.models import Received_Amount
from thefuture.models import Returned_Amount
from thefuture.models import Future_Price
from thefuture.models import Commission_Amount
from thefuture.models import Returned_Tx_To_Returned_Amount_Link
from thefuture.models import Returned_Tx
from thefuture.models import Commission_Tx
from thefuture.models import Commission_Tx_Link
from thefuture.settings import FEE, COMMISSION, COMMISSION_ADDRESS, DATETIME_FORMAT

import bitcoinalafuture.util as util

import datetime
import decimal


def find_clear_minute_prices(trades, last_tid, last_price):
    """
    given a series of trades, find any clear minutes in that series and the
    price for that clear_minute
    """
    prices = []
    for trade in trades:
        trade_tid = int(trade["tid"])
        prior_date = util.unix_time_to_datetime_utc(last_tid * 1e-6)
        trade_date = util.unix_time_to_datetime_utc(int(trade["tid"]) * 1e-6)
        clear_minutes = get_clear_minutes(prior_date, trade_date)
        for clear_minute in clear_minutes:
            new_price = {
                'time': clear_minute,
                'price': last_price,
                "rollover_id_a": last_tid,
                "rollover_id_b": trade_tid,
                }
            prices.append(new_price)
        last_tid = trade_tid
        last_price = trade["price"]
    return prices


def get_clear_minutes(earlier_time, later_time):
        """
        Gets all 'clear minutes' that have occured between earlier_time
        and later_time. Returns an array of clear minute datetimes. A 'clear
        minute' is any time with seconds and microseconds as zero.
        In the case that the earlier or later time itself is a clear minute,
        the set of .-----o is used ie inclusive of earlier time, exclusive of
        later time.
        """
        times = []
        seconds_since_min = datetime.timedelta(0, earlier_time.second, earlier_time.microsecond)
        one_minute = datetime.timedelta(0, 60, 0)
        if(seconds_since_min.total_seconds() != 0):
            nearest_min = earlier_time - seconds_since_min + one_minute
        else:
            nearest_min = earlier_time
        while (nearest_min < later_time):
            times.append(nearest_min)
            nearest_min = nearest_min + one_minute
        return times

def evaluate_amounts_received_after_window_closes():
    """
    Finds any amount which is
    - received on or after the Future_Price window closes and
    - has not yet been returned and
    - has at least 6 confirmations
    Return it to itself.    
    """
    received_amounts = Received_Amount.objects.filter(confirmations__gte=6, returned_amount__isnull=True, time__gte=F('prediction__future_price__time_window_closes'))
    for received_amount in received_amounts:
        returned_amount = {
            "amount": received_amount.amount,
            "from_received_amount": received_amount,
            "to_prediction": received_amount.prediction,
            }
        returned_amount_obj = Returned_Amount(**returned_amount)
        returned_amount_obj.save()

def get_latest_bitcoin_time():
    try:
        latest_bitcoin_price = Bitcoin_Price.objects.order_by('-time')[0]
        latest_bitcoin_time = latest_bitcoin_price.time
    except IndexError:
        latest_bitcoin_time = datetime.datetime(1970, 1, 2, 0, 0, 0, 0, utc)
    return latest_bitcoin_time
            
def get_unresolved_future_prices():
    """
    Get any Future_Prices which have
    - no return amounts which are from received amounts before the window closed
    - some received amounts from before the window closed
    - a valid bitcoin price at the time of the future price
    NB there may be returned amounts from after the window closes but before
    the prediction is evaluated, but these do not mean the future_price is
    resolved
    """
    #TODO this is inefficient, hits the db A LOT
    latest_bitcoin_time = get_latest_bitcoin_time()

    potentially_unresolved = Future_Price.objects.filter(
        time_to_match_price__lte=latest_bitcoin_time
        #TODO would like a __gt condition somehow
    )

    unresolved_future_prices = []
    for p in potentially_unresolved:
        has_no_returned_amounts_from_before_window = Returned_Amount.objects.filter(to_prediction__future_price=p, from_received_amount__time__lt=F('from_received_amount__prediction__future_price__time_window_closes')).count() == 0
        if has_no_returned_amounts_from_before_window:
            has_received_amounts_from_before_window = Received_Amount.objects.filter(prediction__future_price=p, time__lt=F('prediction__future_price__time_window_closes')).count() > 0
            if has_received_amounts_from_before_window:
                bitcoin_price_exists = Bitcoin_Price.objects.filter(time=p.time_to_match_price).count() == 1
                if bitcoin_price_exists:
                    unresolved_future_prices.append(p)

    return unresolved_future_prices

    """
    The following commented-out method:
    - assumes that there is always a bitcoin_price for every minute before the
    last bitcoin_price
    - assumes that every future_prediction before the last returned_amount has
    been evaluated
    ...I am not willing to make these assumptions
    
    latest_bitcoin_time = get_latest_bitcoin_time()

    try:
        latest_returned_amount = Returned_Amount.objects.order_by('-from_received_amount__prediction__future_price__time_to_match_price')[0]
        latest_returned_time = latest_returned_amount.from_received_amount.prediction.future_price.time_to_match_price
    except IndexError:
        latest_returned_time = datetime.datetime(1970, 1, 1, 0, 0, 0, 0, utc)

    unresolved_future_prices = Future_Price.objects.filter(
        time_to_match_price__lte=latest_bitcoin_time,
        time_to_match_price__gt=latest_returned_time
    )

    return unresolved_future_prices
    """



@transaction.commit_on_success
def evaluate_winners_and_losers(future_price):
    """
    This function creates Returned_Amount objects according to who wins
    and loses the future_price wager.
    Winners always get their initial deposit back.
    The loser payments go to the winners in chronological order, until the
    winner has received up to their original deposit amount (less commission),
    and then the next winner begins to receive loser payouts, until there
    are no more loser payments to make.
    If there are more losers than winners, the losers who are not paid to
    winners are returned to the losers.
    """

    winners = []
    losers = []

    target_price = future_price.target_price
    try:
        actual_price_obj = Bitcoin_Price.objects.get(time=future_price.time_to_match_price)
    except:
        return # there is no bitcoin price for this time so this future_price cannot be evaluated
    actual_price = actual_price_obj.price
    price_is_less_than_target = actual_price < target_price
    price_is_equal_to_target = target_price == actual_price

    amounts = Received_Amount.objects.filter(
        amount__gt=0,
        prediction__future_price=future_price,
        time__lt=future_price.time_window_closes
    ).order_by('time', 'id')

    # Split into winners and losers
    for received_amount in amounts:
        guessed_correctly = (received_amount.prediction.price_will_be_less_than_target and price_is_less_than_target) or \
            (not received_amount.prediction.price_will_be_less_than_target and not price_is_less_than_target)
        if guessed_correctly:
            # This is a winner
            returned_amount = {
                "amount": received_amount.amount,
                "from_received_amount": received_amount,
                "to_prediction": received_amount.prediction,
                }
            returned_amount_obj = Returned_Amount(**returned_amount)
            returned_amount_obj.save()
            winners.append({
                "received_amount": received_amount,
                "from_losers": 0
                })
        elif price_is_equal_to_target:
            # Eligible for refund but not for winnings
            # TODO: If the received amount is not confirmed, it will still be
            # returned
            returned_amount = {
                "amount": received_amount.amount,
                "from_received_amount": received_amount,
                "to_prediction": received_amount.prediction,
                }
            returned_amount_obj = Returned_Amount(**returned_amount)
            returned_amount_obj.save()
        else:
            # Record this so in the next step this can be allocated to winners
            losers.append({
                "received_amount": received_amount,
                "to_winners": 0,
                "commission": 0
                })

    for loser in losers:
        # Pay the winners
        for winner in winners:
            loser_funds_remaining = loser["received_amount"].amount - loser["to_winners"] - loser["commission"]
            loser_is_broke = loser_funds_remaining == 0
            if loser_is_broke:
                break
            winner_received_from_losers = winner["from_losers"]
            winner_total_owed_from_losers = winner["received_amount"].amount * (1-COMMISSION)
            amount_remaining_to_pay_winner = winner_total_owed_from_losers - winner_received_from_losers
            if amount_remaining_to_pay_winner > 0:
                amount_to_pay_winner = min(amount_remaining_to_pay_winner, loser_funds_remaining * (1-COMMISSION))
                commission = amount_to_pay_winner / (1-COMMISSION) * COMMISSION
                loser["to_winners"] = loser["to_winners"] + amount_to_pay_winner
                loser["commission"] = loser["commission"] + commission
                winner["from_losers"] = winner["from_losers"] + amount_to_pay_winner
                returned_amount = {
                    "amount": amount_to_pay_winner,
                    "from_received_amount": loser["received_amount"],
                    "to_prediction": winner["received_amount"].prediction,
                    }
                returned_amount_obj = Returned_Amount(**returned_amount)
                returned_amount_obj.save()

                commission_amount = {
                    "returned_amount": returned_amount_obj,
                    "amount": commission
                    }
                commission_amount_obj = Commission_Amount(**commission_amount)
                commission_amount_obj.save()
        # Return any amount remaining after all the winners are paid
        loser_funds_remaining = loser["received_amount"].amount - loser["to_winners"] - loser["commission"]
        if loser_funds_remaining > 0:
            returned_amount = {
                "amount": loser_funds_remaining,
                "from_received_amount": loser["received_amount"],
                "to_prediction": loser["received_amount"].prediction,
                }
            returned_amount_obj = Returned_Amount(**returned_amount)
            returned_amount_obj.save()


def get_unpaid_return_amounts():
    unpaid_return_amounts = Returned_Amount.objects.filter(returned_tx_to_returned_amount_link__isnull=True)
    return unpaid_return_amounts

def gather_returns_by_address(amounts_to_return):
    amounts_by_address = {}
    for returned_amount in amounts_to_return:
        return_address = returned_amount.to_prediction.return_address
        amount_to_return = returned_amount.amount
        if return_address not in amounts_by_address:
            amounts_by_address[return_address] = {
                "amount": decimal.Decimal(0),
                "returns": []
            }
        amounts_by_address[return_address]["amount"] += amount_to_return
        amounts_by_address[return_address]["returns"].append(returned_amount)
    return amounts_by_address

@transaction.commit_on_success
def make_return_payment(address, amount_to_return, returned_amounts):
    amount_to_return -= FEE
    if amount_to_return > 0:
        tx_id = util.make_bitcoin_payment(address, amount_to_return)
        if tx_id.find(" ") == -1 and tx_id.lower().find("error") == -1: #TODO this is a poor condition, works but is poor
            actual_fee_paid = get_actual_tx_fee(tx_id)
            returned_tx = {
                "returned_amount": amount_to_return,
                "tx_id": tx_id,
                "fee": actual_fee_paid
                }
            returned_tx_obj = Returned_Tx(**returned_tx)
            returned_tx_obj.save()
            
            for returned_amount in returned_amounts:
                return_link = {
                    "returned_tx": returned_tx_obj,
                    "returned_amount": returned_amount
                    }
                return_link_obj = Returned_Tx_To_Returned_Amount_Link(**return_link)
                return_link_obj.save()
            return returned_tx_obj
        else:
            print "NOT RETURNED:", tx_id
            print "Unreturned address:", address
            print "Unreturned amount:", amount_to_return
            print
    else:
        print "Amount less than 0: %f %s" % (amount_to_return, address)
        returned_tx = {
            "returned_amount": 0,
            "tx_id": "Amount less than 0 - %f" % amount_to_return,
            "fee": 0
            }
        returned_tx_obj = Returned_Tx(**returned_tx)
        returned_tx_obj.save()
        # TODO this amount before fees is left hanging in the wallet.

        for returned_amount in returned_amounts:
            return_link = {
                "returned_tx": returned_tx_obj,
                "returned_amount": returned_amount
                }
            return_link_obj = Returned_Tx_To_Returned_Amount_Link(**return_link)
            return_link_obj.save()

def get_actual_tx_fee(tx_id):
    tx_detail = util.get_bitcoin_transaction_info(tx_id)
    actual_tx_fee = abs(tx_detail["details"][0]["fee"])
    if actual_tx_fee > FEE:
        #TODO log this, I am interested to know
        pass
    return actual_tx_fee
            
@transaction.commit_on_success
def make_commission_payment(unpaid_commissions, total_commission, returned_txs):
    extra_fees = 0
    for r in returned_txs:
        extra_fees += (r.fee - FEE)
    print "Absorbing %f extra fees into commission" % extra_fees
    final_commission = total_commission - FEE - extra_fees
    if final_commission > 0:
        tx_id = util.make_bitcoin_payment(COMMISSION_ADDRESS, final_commission)
        if tx_id.find(" ") == -1 and tx_id.lower().find("error") == -1:
            actual_fee_paid = get_actual_tx_fee(tx_id)
            commission_tx = {
                "amount": total_commission,
                "tx_id": tx_id,
                "fee": actual_fee_paid
                }
            commission_tx_obj = Commission_Tx(**commission_tx)
            commission_tx_obj.save()
            for commission_amount in unpaid_commissions:
                commission_tx_link = {
                    "commission_amount": commission_amount,
                    "commission_tx": commission_tx_obj
                    }
                commission_tx_link_obj = Commission_Tx_Link(**commission_tx_link)
                commission_tx_link_obj.save()
        else:
            print "ERROR SENDING COMMISSION: %s" % tx_id
    

def get_future_price_data(f):
    
    is_open = f.time_window_closes > util.get_utc_time_now()
    precision = "%0.2f"
    number_split_by_dp = str(f.target_price).split(".")
    if len(number_split_by_dp) == 2:
        precision = "%%0.%if" % max(2,len(number_split_by_dp[1].rstrip('0')))
    future_price = {
        'expires': f.time_to_match_price.strftime(DATETIME_FORMAT),
        'js_expires': int(util.datetime_to_unix_time(f.time_to_match_price) * 1e3),
        'is_open': is_open,
        'target_price_str': precision % float(f.target_price),
        'target_price': float(precision % float(f.target_price)),
        'currency_symbol': "$",
        'exchange': f.exchange,
        'currency_code': f.currency_code,
        'deposits': [
            {
                'received_address': d.prediction.receive_address,
                'return_address': d.prediction.return_address,
                'received_address_short': d.prediction.receive_address[:10],
                'return_address_short': d.prediction.return_address[:10],
                'amount': float(d.amount),
                'time_received': d.time.strftime("%Y-%m-%d %H:%M:%S"),
                'js_time_received': int(util.datetime_to_unix_time(d.time) * 1e3),
                'lt': d.prediction.price_will_be_less_than_target,
                'returns': [{
                    'return_address': r.to_prediction.return_address,
                    'return_address_short': r.to_prediction.return_address[:10],
                    'return_amount': float(r.amount),
                    'is_unpaid': Returned_Tx_To_Returned_Amount_Link.objects.filter(returned_amount=r).count() == 0,
                    } for r in Returned_Amount.objects.filter(from_received_amount=d)]
                } for d in Received_Amount.objects.filter(prediction__future_price=f).order_by('time', 'id')]
    }
    future_price["has_unpaid_returns"] = False
    for deposit in future_price['deposits']:
        for returned_amount in deposit['returns']:
            if returned_amount['is_unpaid']:
                future_price["has_unpaid_returns"] = True
                break
        if future_price["has_unpaid_returns"]:
            break
    future_price["total_more_than"] = sum([d["amount"] for d in future_price["deposits"] if not d["lt"]])
    future_price["total_less_than"] = sum([d["amount"] for d in future_price["deposits"] if d["lt"]])
    actual_price = Bitcoin_Price.objects.filter(time=f.time_to_match_price)
    if len(actual_price) == 1:
        future_price["actual_price"] = float(actual_price[0].price)
        future_price["actual_price_url"] = "https://mtgox.com/api/1/BTCUSD/trades?since=%i" % (actual_price[0].rollover_id_a-1)
    else:
        future_price["actual_price"] = None
    return future_price
    