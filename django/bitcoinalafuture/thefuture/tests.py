"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".

Replace this with more appropriate tests for your application.
"""

from django.test import TestCase
from django.utils.timezone import utc
from django.db.models import Sum

from thefuture.models import Future_Price, Prediction, Bitcoin_Price, Received_Amount, Returned_Amount
from thefuture.funcs import get_clear_minutes
from thefuture.funcs import get_unresolved_future_prices
from thefuture.funcs import evaluate_winners_and_losers
from thefuture.funcs import get_unpaid_return_amounts
from thefuture.funcs import evaluate_amounts_received_after_window_closes
from thefuture.funcs import get_latest_bitcoin_time
from thefuture.funcs import find_clear_minute_prices
from thefuture.settings import FEE, COMMISSION, FUTURE_WINDOW

import bitcoinalafuture.util as util

import datetime
import decimal
import json

ONE_H = datetime.timedelta(0,60*60)
ONE_US = datetime.timedelta(0,0,1)
ONE_M = datetime.timedelta(0,60)

class BalfTestCase(TestCase):

    trades = []

    def future_price(self, **k):
        expiry_time = k["time_to_match_price"] if "time_to_match_price" in k else datetime.datetime(2000, 1, 1, 0, 0, 0, 0, utc)
        window_closes = k["time_window_closes"] if "time_window_closes" in k else expiry_time - datetime.timedelta(0,FUTURE_WINDOW)
        f = Future_Price.objects.create(
            target_price=k["target_price"] if "target_price" in k else 1,
            time_to_match_price=expiry_time,
            time_window_closes=window_closes,
        )
        return f

    def prediction(self, future_price, **k):
        p = Prediction.objects.create(
            future_price=future_price,
            receive_address=k["receive_address"] if "receive_address" in k else "TEST_RECEIVE_ADDRESS",
            return_address=k["return_address"] if "return_address" in k else "TEST_RETURN_ADDRESS",
            price_will_be_less_than_target=k["price_will_be_less_than_target"] if "price_will_be_less_than_target" in k else True
        )
        return p

    def received_amount(self, prediction, **k):
        received_time = prediction.future_price.time_to_match_price - datetime.timedelta(0,FUTURE_WINDOW + 60*60)
        a = Received_Amount.objects.create(
            prediction=prediction,
            amount=k["amount"] if "amount" in k else 1,
            time=k["time"] if "time" in k else received_time,
            tx_id = k["tx_id"] if "tx_id" in k else "TEST_TX_ID",
            confirmations =  k["confirmations"] if "confirmations" in k else 6,
        )
        return a

    def returned_amount(self, received_amount, **k):
        a = Returned_Amount.objects.create(
            amount=k["amount"] if "amount" in k else received_amount.amount,
            from_received_amount=k["from_received_amount"] if "from_received_amount" in k else received_amount,
            to_prediction=k["to_prediction"] if "to_prediction" in k else received_amount.prediction,
        )
        return a

    def bitcoin_price(self, future_price, **k):
        t = k["time"] if "time" in k else future_price.time_to_match_price
        n_bitcoin_prices = Bitcoin_Price.objects.filter(time=t).count()
        if n_bitcoin_prices == 0:
            t_a = util.datetime_to_unix_time(t) * 1e6 - 5
            t_b = util.datetime_to_unix_time(t) * 1e6 + 5
            b = Bitcoin_Price.objects.create(
                time=t,
                price=k["price"] if "price" in k else 1,
                rollover_id_a=k["rollover_id_a"] if "rollover_id_a" in k else t_a,
                rollover_id_b=k["rollover_id_b"] if "rollover_id_b" in k else t_b,
            )
            return b

    def trade(self, **k):
        d = k["date"] if "date" in k else util.datetime_to_unix_time(util.get_utc_time_now())
        t = {
            "date": d,
            "price": k["price"] if "price" in k else 1,
            "amount": k["amount"] if "amount" in k else 1,
            "price_int": k["price_int"] if "price_int" in k else 1e5,
            "amount_int": k["amount_int"] if "amount_int" in k else 1e8,
            "tid": k["tid"] if "tid" in k else d*1e6,
            "price_currency": k["price_currency"] if "price_currency" in k else "USD",
            "item": k["item"] if "item" in k else "BTC",
            "trade_type": k["trade_type"] if "trade_type" in k else "bid",
            "primary": k["primary"] if "primary" in k else "Y",
            "properties": k["properties"] if "properties" in k else "limit",
            }
        self.trades.append(t)


"""
get_unresolved_future_prices
"""

class Get_Unresolved_Future_Prices_No_Matches(BalfTestCase):
    # Future_Prices that do not have a bitcoin price are not detected for
    # evaluation.
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        self.received_amount(p)

    def test(self):
        future_prices = get_unresolved_future_prices()
        self.assertEqual(len(future_prices), 0)

class Get_Unresolved_Future_Prices_Single_Basic_Match(BalfTestCase):
    # Predictions that have no return amounts, have a bitcoin price, and have
    # some received amounts before the window closes should be detected for
    # evaluation.
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        self.received_amount(p)
        self.bitcoin_price(f)

    def test(self):
        future_prices = get_unresolved_future_prices()
        self.assertEqual(len(future_prices), 1)

class Get_Unresolved_Future_Prices_With_Returned_Amount_After_Window_Closes(BalfTestCase):
    # Predictions that have return amounts from in the window period, have a
    # bitcoin price, and have some received amounts before the window closes
    # should still be detected for evaluation.
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        self.received_amount(p)
        self.bitcoin_price(f)
        
        p_2 = self.prediction(f)
        # Add a second received amount just inside the window period.
        rc = self.received_amount(p_2, time=f.time_window_closes + ONE_US)
        rt = self.returned_amount(rc)

    def test(self):
        future_prices = get_unresolved_future_prices()
        self.assertEqual(len(future_prices), 1)

class Get_Unresolved_Future_Prices_With_Only_Received_Amount_After_Window_Closes(BalfTestCase):
    # Predictions that have only return amounts in the window period, have a
    # bitcoin price, but have no pre-window received amounts should not be
    # detected for evaluation.
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        self.bitcoin_price(f)
        
        # Add a received amount just inside the window period.
        rc = self.received_amount(p, time=f.time_window_closes + ONE_US)
        rt = self.returned_amount(rc)

    def test(self):
        future_prices = get_unresolved_future_prices()
        self.assertEqual(len(future_prices), 0)

class Get_Unresolved_Future_Prices_With_Returned_Amount_After_Expiry(BalfTestCase):
    # Predictions that have return amounts from after the expiry, have a
    # bitcoin price, and have some received amounts before the window closes
    # should still be detected for evaluation.
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        self.received_amount(p)
        self.bitcoin_price(f)
        
        p_2 = self.prediction(f)
        # Add a second received amount just inside the window period.
        rc = self.received_amount(p_2, time=f.time_to_match_price + ONE_US)
        rt = self.returned_amount(rc)

    def test(self):
        future_prices = get_unresolved_future_prices()
        self.assertEqual(len(future_prices), 1)

class Get_Unresolved_Future_Prices_With_Only_Received_Amount_After_Expiry(BalfTestCase):
    # Predictions that have only return amounts from after the expiry, have a
    # bitcoin price, but have no pre-window received amounts should not be
    # detected for evaluation.
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        self.bitcoin_price(f)
        
        # Add a received amount just after the expiry time.
        rc = self.received_amount(p, time=f.time_to_match_price + ONE_US)
        # No returned amount because this is not yet a confirmed amount

    def test(self):
        future_prices = get_unresolved_future_prices()
        self.assertEqual(len(future_prices), 0)

class Get_Unresolved_Future_Prices_Single_Too_Old(BalfTestCase):
    # Predictions that are already evaluated are not detected for evaluation.
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        r = self.received_amount(p)
        self.returned_amount(r)
        self.bitcoin_price(f)

    def test(self):
        future_prices = get_unresolved_future_prices()
        self.assertEqual(len(future_prices), 0)
        
class Get_Unresolved_Future_Prices_Mutli_Prediction(BalfTestCase):
    # If there are multiple future_prices, all valid future_prices are detected
    # for evaluation
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        self.received_amount(p)
        self.bitcoin_price(f)
        
        # Make a second future_price. Both this and the init future_price
        # should be detected for evaluation
        f_2 = self.future_price(target_price=2)
        p_2 = self.prediction(f_2)
        self.received_amount(p_2)
        
    def test(self):
        future_prices = get_unresolved_future_prices()
        self.assertEqual(len(future_prices), 2)

class Get_Unresolved_Future_Prices_No_Received_Amounts(BalfTestCase):
    # If there are no received amounts the future price should not be detected
    # for evaluation
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        self.bitcoin_price(f)
        
    def test(self):
        future_prices = get_unresolved_future_prices()
        self.assertEqual(len(future_prices), 0)

"""
evaluate_winners_and_losers
"""
class Evaluate_Winners_And_Losers_Basic_Match_More_Than_Is_Winner(BalfTestCase):
    # This is the simplest matching case between winners and losers.
    # Two predictions on the price, both on $1/BTC, however the actual price
    # is $1.5, so the More Than prediction wins. The amounts for each
    # participant are equal.
    # This tests when the winner is the one who picked that the target price
    # will be greater than the actual price
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        self.received_amount(p)
        self.bitcoin_price(f, price=1.5)
        
        p_false = self.prediction(f, price_will_be_less_than_target=False)
        rc = self.received_amount(p_false)
        
    def test(self):
        p_true = Prediction.objects.filter(price_will_be_less_than_target=True)[0]
        p_false = Prediction.objects.filter(price_will_be_less_than_target=False)[0]

        received_amount_true = Received_Amount.objects.filter(prediction=p_true).aggregate(Sum('amount'))["amount__sum"]
        received_amount_false = Received_Amount.objects.filter(prediction=p_false).aggregate(Sum('amount'))["amount__sum"]
        
        future_prices = get_unresolved_future_prices()
        evaluate_winners_and_losers(future_prices[0])
        
        r = Returned_Amount.objects.all()
        self.assertEqual(r.count(), 2)
        self.assertEqual(r[0].to_prediction, p_false)
        self.assertEqual(r[1].to_prediction, p_false)
        
        expected_total_returned = received_amount_true + received_amount_false * decimal.Decimal(1-COMMISSION)
        actual_total_returned = r[0].amount+r[1].amount
        self.assertEqual(expected_total_returned, actual_total_returned)


class Evaluate_Winners_And_Losers_Basic_Match_Less_Than_Is_Winner(BalfTestCase):
    # This is the simplest matching case between winners and losers.
    # Two predictions on the price, both on $1/BTC, however the actual price
    # is $0.5, so one prediction wins and one prediction loses. The amounts
    # for each participant are equal.
    # This tests when the winner is the one who picked that the target price
    # will be less than the actual price
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        self.received_amount(p)
        self.bitcoin_price(f, price=0.5)
                
        p_false = self.prediction(f, price_will_be_less_than_target=False)
        rc = self.received_amount(p_false)


    def test(self):
        p_true = Prediction.objects.filter(price_will_be_less_than_target=True)[0]
        p_false = Prediction.objects.filter(price_will_be_less_than_target=False)[0]

        received_amount_true = Received_Amount.objects.filter(prediction=p_true).aggregate(Sum('amount'))["amount__sum"]
        received_amount_false = Received_Amount.objects.filter(prediction=p_false).aggregate(Sum('amount'))["amount__sum"]
        
        future_prices = get_unresolved_future_prices()
        evaluate_winners_and_losers(future_prices[0])

        r = Returned_Amount.objects.all()
        self.assertEqual(r.count(), 2)
        self.assertEqual(r[0].to_prediction, p_true)
        self.assertEqual(r[1].to_prediction, p_true)

        expected_total_returned = received_amount_true + received_amount_false * decimal.Decimal(1-COMMISSION)
        actual_total_returned = r[0].amount+r[1].amount
        self.assertEqual(expected_total_returned, actual_total_returned)

class Evaluate_Winners_And_Losers_Basic_Match_Target_Price_Is_Equal(BalfTestCase):
    # This is the simplest matching case between winners and losers.
    # Two predictions on the price, both on $1/BTC, and the actual price
    # is $1, so neither prediction wins or loses. The amounts for each
    # participant are simply returned.
    # This tests that both participants have their amounts returned.
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        self.received_amount(p)
        b = self.bitcoin_price(f)
        
        p_false = self.prediction(f, price_will_be_less_than_target=False)
        rc = self.received_amount(p_false)

    def test(self):
        p_true = Prediction.objects.filter(price_will_be_less_than_target=True)[0]
        p_false = Prediction.objects.filter(price_will_be_less_than_target=False)[0]

        received_amount_true = Received_Amount.objects.filter(prediction=p_true)[0]
        received_amount_false = Received_Amount.objects.filter(prediction=p_false)[0]

        future_prices = get_unresolved_future_prices()
        evaluate_winners_and_losers(future_prices[0])

        r = Returned_Amount.objects.all()
        self.assertEqual(r.count(), 2)

        expected_total_returned = received_amount_true.amount + received_amount_false.amount
        actual_total_returned = r[0].amount+r[1].amount
        self.assertEqual(expected_total_returned, actual_total_returned)

        r = Returned_Amount.objects.filter(from_received_amount=received_amount_true)[0]
        self.assertEqual(r.to_prediction, p_true)

        r = Returned_Amount.objects.filter(from_received_amount=received_amount_false)[0]
        self.assertEqual(r.to_prediction, p_false)


class Evaluate_Winners_And_Losers_Only_One_Winning_Participant(BalfTestCase):
    # If there is only one participant and they win, they are simply refunded
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        self.received_amount(p)
        self.bitcoin_price(f, price=0.5)
        
    def test(self):
        p_true = Prediction.objects.all()[0]
        rc = Received_Amount.objects.filter(prediction=p_true)[0]
        
        future_prices = get_unresolved_future_prices()
        evaluate_winners_and_losers(future_prices[0])

        r = Returned_Amount.objects.all()
        self.assertEqual(r.count(), 1)
        self.assertEqual(r[0].to_prediction, p_true)

        expected_total_returned = rc.amount
        actual_total_returned = r[0].amount
        self.assertEqual(expected_total_returned, actual_total_returned)


class Evaluate_Winners_And_Losers_Only_One_Losing_Participant(BalfTestCase):
    # If there is only one participant and they lose, they are simply refunded
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        self.received_amount(p)
        self.bitcoin_price(f, price=1.5)
        
    def test(self):
        p_true = Prediction.objects.all()[0]
        rc = Received_Amount.objects.filter(prediction=p_true)[0]

        future_prices = get_unresolved_future_prices()
        evaluate_winners_and_losers(future_prices[0])

        r = Returned_Amount.objects.all()
        self.assertEqual(r.count(), 1)
        self.assertEqual(r[0].to_prediction, p_true)

        expected_total_returned = rc.amount
        actual_total_returned = r[0].amount
        self.assertEqual(expected_total_returned, actual_total_returned)

class Evaluate_Winners_And_Losers_After_Window_Closes(BalfTestCase):
    # If a received amount is received after the window closes, the amount
    # does not take part in winners and losers.
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        self.received_amount(p)
        self.bitcoin_price(f)
        
        # Make a second received amount after the initial received amount,
        # which will not be included in the winners and losers analysis
        rc = self.received_amount(p, time=p.future_price.time_window_closes + ONE_US)

    def test(self):
        future_prices = get_unresolved_future_prices()
        evaluate_winners_and_losers(future_prices[0])

        p = Prediction.objects.all()[0]
        rc_before = Received_Amount.objects.filter(time__lt=p.future_price.time_window_closes)[0]
        rc_after = Received_Amount.objects.filter(time__gte=p.future_price.time_window_closes)[0]

        r = Returned_Amount.objects.all()
        self.assertEqual(r.count(), 1)

        r = Returned_Amount.objects.filter(to_prediction=p)
        self.assertEqual(r.count(), 1)

        r = Returned_Amount.objects.filter(from_received_amount=rc_before)
        self.assertEqual(r.count(), 1)

        r = Returned_Amount.objects.filter(from_received_amount=rc_after)
        self.assertEqual(r.count(), 0)

class Evaluate_Winners_And_Losers_Receive_Payment_After_Future_Price_Expires(BalfTestCase):
    # If a received amount is received after the future price expires, the
    # received amount does not take part in winners and losers.
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        self.received_amount(p)
        self.bitcoin_price(f)
        
        # Make a second received amount after the initial received amount,
        # which will not be included in the winners and losers analysis
        rc = self.received_amount(p, time=p.future_price.time_to_match_price + ONE_US)

    def test(self):
        future_prices = get_unresolved_future_prices()
        evaluate_winners_and_losers(future_prices[0])

        p = Prediction.objects.all()[0]
        rc = Received_Amount.objects.filter(time__lt=p.future_price.time_to_match_price)[0]
       
        r = Returned_Amount.objects.all()
        self.assertEqual(r.count(), 1)

        r = Returned_Amount.objects.filter(to_prediction=p)
        self.assertEqual(r.count(), 1)

        r = Returned_Amount.objects.filter(from_received_amount=rc)
        self.assertEqual(r.count(), 1)


        
class Evaluate_Winners_And_Losers_More_Winners_Than_Losers(BalfTestCase):
    # If there are more winnings than losings, the later winnings don't get
    # paid by the losers. ie testing the 'first come first serve' functionality
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        self.received_amount(p)
        self.bitcoin_price(f, price=0.5)
        
        p_false = self.prediction(f, price_will_be_less_than_target=False)
        rc_false = self.received_amount(p_false)

        p_true_2 = self.prediction(f)
        rc_true_2 = self.received_amount(p_true_2)

    def test(self):
        future_prices = get_unresolved_future_prices()
        evaluate_winners_and_losers(future_prices[0])

        p = Prediction.objects.order_by('id')
        p_true_1 = p[0]
        p_false = p[1]
        p_true_2 = p[2]

        rc_true_1 = Received_Amount.objects.filter(prediction=p_true_1)[0]
        rc_false = Received_Amount.objects.filter(prediction=p_false)[0]
        rc_true_2 = Received_Amount.objects.filter(prediction=p_true_2)[0]

        # There should be three returned amounts
        r = Returned_Amount.objects.all()
        self.assertEqual(r.count(), 3)
        expected_total_returned = 1 + 1 * decimal.Decimal(1-COMMISSION) + 1
        actual_total_returned = r[0].amount+r[1].amount+r[2].amount
        self.assertEqual(expected_total_returned, actual_total_returned)

        # The return from received_amount 1 should be returned to prediction 1 (winner)
        r = Returned_Amount.objects.filter(from_received_amount=rc_true_1)
        self.assertEqual(r[0].to_prediction, p_true_1)

        # The return from received_amount 2 should be returned to prediction 1 (loser)
        r = Returned_Amount.objects.filter(from_received_amount=rc_false)
        self.assertEqual(r[0].to_prediction, p_true_1)

        # The return from received_amount 3 should be returned to prediction 3 (winner no loser to match)
        r = Returned_Amount.objects.filter(from_received_amount=rc_true_2)
        self.assertEqual(r[0].to_prediction, p_true_2)

class Evaluate_Winners_And_Losers_More_Losers_Than_Winners(BalfTestCase):
    # If there are more losers than winners, the later losers get their deposit
    # refunded. ie testing the 'first come first loses' functionality
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        self.received_amount(p)
        self.bitcoin_price(f, price=1.5)
        
        p_false = self.prediction(f, price_will_be_less_than_target=False)
        rc_false = self.received_amount(p_false)

        p_true_2 = self.prediction(f)
        rc_true_2 = self.received_amount(p_true_2)

    def test(self):
        future_prices = get_unresolved_future_prices()
        evaluate_winners_and_losers(future_prices[0])

        p = Prediction.objects.order_by('id')
        p_true_1 = p[0]
        p_false = p[1]
        p_true_2 = p[2]

        rc_true_1 = Received_Amount.objects.filter(prediction=p_true_1)[0]
        rc_false = Received_Amount.objects.filter(prediction=p_false)[0]
        rc_true_2 = Received_Amount.objects.filter(prediction=p_true_2)[0]

        # There should be three returned amounts
        r = Returned_Amount.objects.all()
        self.assertEqual(r.count(), 3)
        expected_total_returned = 1 * decimal.Decimal(1-COMMISSION) + 1 + 1
        actual_total_returned = r[0].amount+r[1].amount+r[2].amount
        self.assertEqual(expected_total_returned, actual_total_returned)

        # The return from received_amount 1 should be returned to prediction 2 (loser)
        r = Returned_Amount.objects.filter(from_received_amount=rc_true_1)
        self.assertEqual(r[0].to_prediction, p_false)

        # The return from received_amount 2 should be returned to prediction 2 (winner)
        r = Returned_Amount.objects.filter(from_received_amount=rc_false)
        self.assertEqual(r[0].to_prediction, p_false)

        # The return from received_amount 3 should be returned to prediction 3 (loser no winner to match)
        r = Returned_Amount.objects.filter(from_received_amount=rc_true_2)
        self.assertEqual(r[0].to_prediction, p_true_2)


class Evaluate_Winners_And_Losers_Overlapping_Winners(BalfTestCase):
    # If there is one winner but multiple losers, the winner should get their
    # original deposit back up to the original deposit value (less commission).
    # This case tests when both losers contribute to the winner because there
    # was one large winner and two smaller losers. In this case the second loser
    # receives some of their payment back, because when their payment is
    # combined with the first payment the total is too much to pay the winner.
    # Firstly a winning prediction for 3 is made
    # Secondly a losing prediction for 1 is made
    # Third a losing prediction for 5 is made
    # The result
    # First prediction is refunded
    # Part of first prediction winnings comes from second prediction loss
    # Rest of first prediction winnings comes from third prediction loss
    # Remainder of third prediction loss is refunded to the owner
    def setUp(self):
        f = self.future_price()
        p_true = self.prediction(f)
        p_false_1 = self.prediction(f, price_will_be_less_than_target=False)
        p_false_2 = self.prediction(f, price_will_be_less_than_target=False)
        self.received_amount(p_true, amount=3)
        rc_false_1 = self.received_amount(p_false_1, amount=1)
        self.received_amount(p_false_2, amount=5, time=rc_false_1.time + ONE_US)
        self.bitcoin_price(f, price=0.5)

    def test(self):
        future_prices = get_unresolved_future_prices()
        evaluate_winners_and_losers(future_prices[0])

        p_true = Prediction.objects.filter(price_will_be_less_than_target=True)[0]
        rc_true = Received_Amount.objects.filter(prediction=p_true)[0]

        p_false_1 = Prediction.objects.filter(price_will_be_less_than_target=False, received_amount__amount=1)[0]
        rc_false_1 = Received_Amount.objects.filter(prediction__price_will_be_less_than_target=False, amount=1)[0]

        p_false_2 = Prediction.objects.filter(price_will_be_less_than_target=False, received_amount__amount=5)[0]
        rc_false_2 = Received_Amount.objects.filter(prediction__price_will_be_less_than_target=False, amount=5)[0]

        # There should be four returned amounts
        r = Returned_Amount.objects.all()
        self.assertEqual(r.count(), 4)
        expected_total_returned = 3 + 1 * (1-COMMISSION) + (3 - 1) * (1-COMMISSION) + (5-(3-1))
        actual_total_returned = r[0].amount+r[1].amount+r[2].amount+r[3].amount
        self.assertEqual(expected_total_returned, actual_total_returned)

        # The return from prediction 1 should be returned to prediction 1 (winner)
        r = Returned_Amount.objects.filter(from_received_amount=rc_true)
        self.assertEqual(r[0].to_prediction, p_true)
        self.assertEqual(r[0].amount, 3)

        # The return from prediction 2 should be returned to prediction 1 (loser)
        r = Returned_Amount.objects.filter(from_received_amount=rc_false_1)
        self.assertEqual(r[0].to_prediction, p_true)
        self.assertEqual(r[0].amount, 1*(1-COMMISSION))

        # The return from prediction 3 should be split
        r = Returned_Amount.objects.filter(from_received_amount=rc_false_2)
        self.assertEqual(r.count(), 2)
        # One returned to prediction 1 (loser)
        r = Returned_Amount.objects.filter(from_received_amount=rc_false_2, to_prediction=p_true)
        self.assertEqual(r[0].amount, 2*(1-COMMISSION))
        # One returned to prediction 3 (loser remainder)
        r = Returned_Amount.objects.filter(from_received_amount=rc_false_2, to_prediction=p_false_2)
        self.assertEqual(r[0].amount, 3)


class Evaluate_Winners_And_Losers_Winners_Overlapping_Losers(BalfTestCase):
    # If there is many winners and one loser, the winners should get their
    # original deposit back up to the original deposit value (less commission).
    # This case tests when the loser contributes to more than one winner.
    # Firstly a losing prediction for 4 is made
    # Secondly a winning prediction for 1 is made
    # Third a winning prediction for 2 is made
    # The result
    # First prediction is split between second and third predictions, with
    # some remaining to be refunded to the first prediction
    # All the second prediction is returned
    # All the third prediction is returned
    def setUp(self):
        f = self.future_price()
        p_true = self.prediction(f)
        p_false_1 = self.prediction(f, price_will_be_less_than_target=False)
        p_false_2 = self.prediction(f, price_will_be_less_than_target=False)
        self.received_amount(p_true, amount=4)
        rc_false_1 = self.received_amount(p_false_1, amount=1)
        self.received_amount(p_false_2, amount=2, time=rc_false_1.time + ONE_US)
        self.bitcoin_price(f, price=1.5)

    def test(self):
        future_prices = get_unresolved_future_prices()
        evaluate_winners_and_losers(future_prices[0])

        p_true = Prediction.objects.filter(price_will_be_less_than_target=True)[0]
        rc_true = Received_Amount.objects.filter(prediction=p_true)[0]

        p_false_1 = Prediction.objects.filter(price_will_be_less_than_target=False, received_amount__amount=1)[0]
        rc_false_1 = Received_Amount.objects.filter(prediction__price_will_be_less_than_target=False, amount=1)[0]

        p_false_2 = Prediction.objects.filter(price_will_be_less_than_target=False, received_amount__amount=2)[0]
        rc_false_2 = Received_Amount.objects.filter(prediction__price_will_be_less_than_target=False, amount=2)[0]

        # There should be five returned amounts
        r = Returned_Amount.objects.all()
        self.assertEqual(r.count(), 5)
        expected_total_returned = 1 * (1-COMMISSION) + 2 * (1-COMMISSION) + (4 - 1 - 2) + 1 + 2
        actual_total_returned = r[0].amount+r[1].amount+r[2].amount+r[3].amount+r[4].amount
        self.assertEqual(expected_total_returned, actual_total_returned)

        # The return from prediction 2 should be returned to prediction 2 (winner)
        r = Returned_Amount.objects.filter(from_received_amount=rc_false_1)
        self.assertEqual(r[0].to_prediction, p_false_1)
        self.assertEqual(r[0].amount, 1)

        # The return from prediction 3 should be returned to prediction 3 (winner)
        r = Returned_Amount.objects.filter(from_received_amount=rc_false_2)
        self.assertEqual(r[0].to_prediction, p_false_2)
        self.assertEqual(r[0].amount, 2)

        # The return from prediction 1 should be split three ways
        r = Returned_Amount.objects.filter(from_received_amount=rc_true)
        self.assertEqual(r.count(), 3)
        # One returned to prediction 1 (loser remainder)
        r = Returned_Amount.objects.filter(from_received_amount=rc_true, to_prediction=p_true)
        self.assertEqual(r[0].to_prediction, p_true)
        self.assertEqual(r[0].amount, 1)
        # One returned to prediction 2 (loser)
        r = Returned_Amount.objects.filter(from_received_amount=rc_true, to_prediction=p_false_1)
        self.assertEqual(r[0].amount, 1*(1-COMMISSION))
        # One returned to prediction 3 (loser)
        r = Returned_Amount.objects.filter(from_received_amount=rc_true, to_prediction=p_false_2)
        self.assertEqual(r[0].amount, 2*(1-COMMISSION))


"""
TODO test received amounts at exactly the same time
"""









"""
Get_Unpaid_Returned_Amounts
"""
        
class Get_Unpaid_Returned_Amounts_Simple_Test(BalfTestCase):
    # Tests that unpaid return amounts are detected. Simplest case of one
    # prediction, no previous or future predictions, one return amount.
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        self.received_amount(p)
        b = self.bitcoin_price(f)

    def test(self):
        future_prices = get_unresolved_future_prices()
        for f in future_prices:
            evaluate_winners_and_losers(f)
        r = get_unpaid_return_amounts()
        self.assertEqual(r.count(), 1)

"""
TODO consider more cases for Get_Unpaid_Returned_Amounts
"""
        
"""
Get_Clear_Minutes
"""

class Get_Clear_Minutes_Test(TestCase):
    def test_clear_minutes(self):
        # Times both in the same minute.
        a = datetime.datetime(2012, 1, 1, 4, 4, 2, 432434)
        b = datetime.datetime(2012, 1, 1, 4, 4, 5, 432434)
        x = get_clear_minutes(a, b)
        self.assertEqual(x, [])

        # Times between one tickover period
        a = datetime.datetime(2012, 1, 1, 4, 3, 33, 432434)
        b = datetime.datetime(2012, 1, 1, 4, 4, 5, 432434)
        x = get_clear_minutes(a, b)
        self.assertEqual(x, [datetime.datetime(2012, 1, 1, 4, 4, 0, 0)])

        # Times between multiple tickover periods
        a = datetime.datetime(2012, 1, 1, 4, 0, 33, 432434)
        b = datetime.datetime(2012, 1, 1, 4, 4, 5, 432434)
        x = get_clear_minutes(a, b)
        self.assertEqual(x, [
            datetime.datetime(2012, 1, 1, 4, 1, 0, 0),
            datetime.datetime(2012, 1, 1, 4, 2, 0, 0),
            datetime.datetime(2012, 1, 1, 4, 3, 0, 0),
            datetime.datetime(2012, 1, 1, 4, 4, 0, 0),
        ])

        # Later time exactly on the tickover
        a = datetime.datetime(2012, 1, 1, 4, 3, 58, 432434)
        b = datetime.datetime(2012, 1, 1, 4, 4, 0, 0)
        x = get_clear_minutes(a, b)
        self.assertEqual(x, [])

        # Earlier time exactly on the tickover
        a = datetime.datetime(2012, 1, 1, 4, 4, 0, 0)
        b = datetime.datetime(2012, 1, 1, 4, 4, 45, 342334)
        x = get_clear_minutes(a, b)
        self.assertEqual(x, [datetime.datetime(2012, 1, 1, 4, 4, 0, 0)])

        # Both times exactly on the tickover
        a = datetime.datetime(2012, 1, 1, 4, 3, 0, 0)
        b = datetime.datetime(2012, 1, 1, 4, 4, 0, 0)
        x = get_clear_minutes(a, b)
        self.assertEqual(x, [datetime.datetime(2012, 1, 1, 4, 3, 0, 0)])

        # Times are the same and on a tickover
        a = datetime.datetime(2012, 1, 1, 4, 4, 0, 0)
        b = datetime.datetime(2012, 1, 1, 4, 4, 0, 0)
        x = get_clear_minutes(a, b)
        self.assertEqual(x, [])



"""
evaluate_amounts_received_after_window_closes
"""
class Evaluate_Amounts_Received_After_Window_Closes_Before_Window(BalfTestCase):
    # If an amount is received before the window closes it is not evaluated
    # as an amount received after the window closes
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        rc = self.received_amount(p)
        b = self.bitcoin_price(f)

    def test(self):
        evaluate_amounts_received_after_window_closes()
        r = Returned_Amount.objects.count()
        self.assertEqual(r, 0)

class Evaluate_Amounts_Received_After_Window_Closes_Equal_To_Window(BalfTestCase):
    # If an amount is received exactly when the window closes it is evaluated
    # as an amount received after the window closes
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        rc = self.received_amount(p, time=f.time_window_closes)
        b = self.bitcoin_price(f)

    def test(self):
        evaluate_amounts_received_after_window_closes()
        r = Returned_Amount.objects.count()
        self.assertEqual(r, 1)

class Evaluate_Amounts_Received_After_Window_Closes_Before_Expiry_After_Window(BalfTestCase):
    # If an amount is received after the window closes it is evaluated
    # as an amount received after the window closes
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        rc = self.received_amount(p, time=f.time_window_closes+ONE_US)
        b = self.bitcoin_price(f)

    def test(self):
        evaluate_amounts_received_after_window_closes()
        r = Returned_Amount.objects.count()
        self.assertEqual(r, 1)
        
class Evaluate_Amounts_Received_After_Window_Closes_After_Expiry(BalfTestCase):
    # If an amount is received after the future_price expires it is evaluated
    # as an amount received after the window closes
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        rc = self.received_amount(p, time=f.time_to_match_price+ONE_US)
        b = self.bitcoin_price(f)

    def test(self):
        evaluate_amounts_received_after_window_closes()
        r = Returned_Amount.objects.count()
        self.assertEqual(r, 1)
        
class Evaluate_Amounts_Received_After_Window_Closes_Many_Amounts(BalfTestCase):
    # If there are multiple received amounts, they are all evaluated as
    # received after the window closes
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        b = self.bitcoin_price(f)

        # Not evaluated
        self.received_amount(p, time=f.time_window_closes-ONE_US*1)
        self.received_amount(p, time=f.time_window_closes-ONE_US*2)
        self.received_amount(p, time=f.time_window_closes-ONE_US*3)

        # Evaluated
        self.received_amount(p, time=f.time_window_closes+ONE_US*1)
        self.received_amount(p, time=f.time_window_closes+ONE_US*2)
        self.received_amount(p, time=f.time_window_closes+ONE_US*3)
        self.received_amount(p, time=f.time_window_closes+ONE_US*4)
        self.received_amount(p, time=f.time_window_closes+ONE_US*5)

    def test(self):
        evaluate_amounts_received_after_window_closes()
        r = Returned_Amount.objects.count()
        self.assertEqual(r, 5)

class Evaluate_Amounts_Received_After_Window_Closes_Not_Enough_Confirmation(BalfTestCase):
    # If an amount is received after the future_price expires and it hasn't
    # been confirmed with at least 6 confirmations, it is not evaluated
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        rc = self.received_amount(p, time=f.time_to_match_price+ONE_US, confirmations=5)
        rc = self.received_amount(p, time=f.time_to_match_price+ONE_US, confirmations=4)
        rc = self.received_amount(p, time=f.time_to_match_price+ONE_US, confirmations=3)
        rc = self.received_amount(p, time=f.time_to_match_price+ONE_US, confirmations=2)
        rc = self.received_amount(p, time=f.time_to_match_price+ONE_US, confirmations=1)
        rc = self.received_amount(p, time=f.time_to_match_price+ONE_US, confirmations=0)
        b = self.bitcoin_price(f)

    def test(self):
        evaluate_amounts_received_after_window_closes()
        r = Returned_Amount.objects.count()
        self.assertEqual(r, 0)

class Evaluate_Amounts_Received_After_Window_Closes_Not_Enough_Confirmation(BalfTestCase):
    # If an amount is received after the future_price has more than 6 confirmations
    # it is evaluated. Usually received amounts only have 6 confirmations and are
    # no longer checked after that
    def setUp(self):
        f = self.future_price()
        p = self.prediction(f)
        rc = self.received_amount(p, time=f.time_to_match_price+ONE_US, confirmations=999)
        b = self.bitcoin_price(f)

    def test(self):
        evaluate_amounts_received_after_window_closes()
        r = Returned_Amount.objects.count()
        self.assertEqual(r, 1)

"""
get_latest_bitcoin_time
"""
class Get_Latest_Bitcoin_Time_No_Existing_Times(BalfTestCase):
    # If there is no existing time, a time before bitcoin existed is returned
    def setUp(self):
        pass
    
    def test(self):
        t = get_latest_bitcoin_time()
        self.assertTrue(t < datetime.datetime(2009,1,1,0,0,0,0,utc))
    
class Get_Latest_Bitcoin_Time_One_Existing_Time(BalfTestCase):
    # If there is only one bitcoin time, this is returned as the latest time
    def setUp(self):
        f = self.future_price()
        b = self.bitcoin_price(f)

    def test(self):
        f = Future_Price.objects.all()[0]
        t = get_latest_bitcoin_time()
        self.assertTrue(t == f.time_to_match_price)

class Get_Latest_Bitcoin_Time_Many_Ordered_Existing_Times(BalfTestCase):
    # If there are many bitcoin times, the latest one is returned
    def setUp(self):
        f = self.future_price()
        self.bitcoin_price(f)
        self.bitcoin_price(f, time=f.time_to_match_price+(1*ONE_US))
        self.bitcoin_price(f, time=f.time_to_match_price+(2*ONE_US))
        self.bitcoin_price(f, time=f.time_to_match_price+(3*ONE_US))
        self.bitcoin_price(f, time=f.time_to_match_price+(4*ONE_US))

    def test(self):
        f = Future_Price.objects.all()[0]
        t = get_latest_bitcoin_time()
        self.assertTrue(t == f.time_to_match_price + (4*ONE_US))
    
class Get_Latest_Bitcoin_Time_Many_Unordered_Existing_Times(BalfTestCase):
    # If earlier bitcoin prices are added to the database, they do not affect
    # the fetching of the latest price
    def setUp(self):
        f = self.future_price()
        self.bitcoin_price(f)
        self.bitcoin_price(f, time=f.time_to_match_price+(2*ONE_US))
        self.bitcoin_price(f, time=f.time_to_match_price+(4*ONE_US))
        self.bitcoin_price(f, time=f.time_to_match_price+(1*ONE_US))
        self.bitcoin_price(f, time=f.time_to_match_price+(3*ONE_US))

    def test(self):
        f = Future_Price.objects.all()[0]
        t = get_latest_bitcoin_time()
        self.assertTrue(t == f.time_to_match_price + (4*ONE_US))

"""
find_clear_minute_prices
"""
class Find_Clear_Minute_Prices_One_Clear_Minute(BalfTestCase):
    # If there is one clear minute in the trades it is detected
    def setUp(self):
        self.d = util.datetime_to_unix_time(datetime.datetime(2012,1,1,2,2,2,123,utc))
        self.trade(date=self.d, price=1)
        self.trade(date=self.d+ONE_M.total_seconds(), price=2)
    
    def test(self):
        last_tid = self.d * 1e6 - 1
        last_price = 0.5
        p = find_clear_minute_prices(self.trades, last_tid, last_price)
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["price"], 1)
        self.assertEqual(p[0]["time"], datetime.datetime(2012,1,1,2,3,0,0,utc))
        
        
#class Find_Clear_Minute_Prices_No_Clear_Minutes(BalfTestCase):
#class Find_Clear_Minute_Prices_Many_Clear_Minutes(BalfTestCase):
#class Find_Clear_Minute_Prices_First_tid_Is_Clear_Minute(BalfTestCase):
#class Find_Clear_Minute_Prices_Last_tid_Is_Clear_Minute(BalfTestCase):
#class Find_Clear_Minute_Prices_No_Trades(BalfTestCase):
#class Find_Clear_Minute_Prices_One_Trade(BalfTestCase):

"""
gather_returns_by_address
"""
#class Gather_Returns_By_Address_No_Returns(BalfTestCase):
#class Gather_Returns_By_Address_One_Returns(BalfTestCase):
#class Gather_Returns_By_Address_Multiple_Returns_Same_Address(BalfTestCase):
#class Gather_Returns_By_Address_Multiple_Returns_Different_Address(BalfTestCase):

"""
make_return_payment
"""
#If there's the tx_id is not an error
#If there's the tx_id is an error

"""
make_commission_payment
"""
#If there's the tx_id is not an error
#If there's the tx_id is an error
    