from django.core.management.base import BaseCommand, CommandError

from thefuture.funcs import get_unpaid_return_amounts
from thefuture.funcs import gather_returns_by_address
from thefuture.funcs import make_return_payment
from thefuture.funcs import make_commission_payment
from thefuture.models import Commission_Amount

from thefuture.settings import COMMISSION_ADDRESS

import bitcoinalafuture.util as util

import decimal
import subprocess




"""
Gets all the unpaid return_amounts and pays them.
Also pays out the commission.
This script is manually run only after the wallet is manually unlocked.
"""

class Command(BaseCommand):
    
    amounts_to_return = get_unpaid_return_amounts()
    
    def handle(self, *args, **options):
        if already_running():
            self.stdout.write("Already running")
            return
        time_script_started = util.get_utc_time_now()
        
        #Perform a sanity check
        self.check_payments_less_than_amount_in_wallet()
        self.check_payments_less_than_receives()
        (unpaid_commissions, total_commission) = self.get_unpaid_commissions()
        self.check_for_unconfirmed_receives()

        #Manually say it's OK
        responses_to_continue = ["y", ""]
        if raw_input("Do you want to continue? [Yn] ") not in responses_to_continue:
            print "Cancelled. No transactions made"
            return

        #Make the returns
        returns_by_address = gather_returns_by_address(self.amounts_to_return)

        returned_txs = []
        for address in returns_by_address:
            amount = returns_by_address[address]["amount"]
            returned_amounts = returns_by_address[address]["returns"]
            returned_tx = make_return_payment(address, amount, returned_amounts)
            if returned_tx is not None:
                returned_txs.append(returned_tx)

        # make commission payment
        make_commission_payment(unpaid_commissions, total_commission, returned_txs)

        # TODO send to cold storage


    def check_payments_less_than_amount_in_wallet(self):
        #Check that amount to go out < amount in wallet
        amount_in_wallet_str = util.get_wallet_balance()
        #TODO this is a terrible way to check for errors
        try:
            amount_in_wallet = float(amount_in_wallet_str)
        except ValueError:
            amount_in_wallet = -1

        total_to_be_paid = decimal.Decimal(0)
        for amount_to_return in self.amounts_to_return:
            total_to_be_paid += amount_to_return.amount

        print "Total to pay: ", total_to_be_paid, "Total in wallet: ", amount_in_wallet
        if total_to_be_paid > amount_in_wallet:
            raise ValueError("total to be paid > amount in wallet %f > %f" % (total_to_be_paid, amount_in_wallet))

    def check_payments_less_than_receives(self):
        #Check that amount to go out <= unpaid received amounts before now
        total_received = decimal.Decimal(0)
        total_to_be_paid = decimal.Decimal(0)
        received_already_checked = {}
        for amount_to_return in self.amounts_to_return:
            total_to_be_paid += amount_to_return.amount
            if amount_to_return.from_received_amount not in received_already_checked:
                total_received += amount_to_return.from_received_amount.amount
                received_already_checked[amount_to_return.from_received_amount] = None            

        print "Total to pay: ", total_to_be_paid, "Total received: ", total_received
        if total_to_be_paid > total_received:
            raise ValueError("total to be paid > total received")

    def check_for_unconfirmed_receives(self):
        unconfirmed = self.amounts_to_return.filter(from_received_amount__confirmations__lt=6)
        total_unconfirmed_amount = sum([x.from_received_amount.amount for x in unconfirmed])
        print "Unconfirmed: %i instances totalling %f (will be paid)" % (len(unconfirmed), total_unconfirmed_amount)

    def get_unpaid_commissions(self):
        unpaid_commissions = Commission_Amount.objects.filter(commission_tx_link__isnull=True)
        total_commission = sum([u.amount for u in unpaid_commissions])
        print "Paying commission of %f to %s" % (total_commission, COMMISSION_ADDRESS)
        return (unpaid_commissions, total_commission)



def already_running():
    pid = subprocess.Popen(["ps -ef | grep make_payments | grep -v grep", ""], stdout=subprocess.PIPE, shell=True).stdout.read()
    if(len(pid.split('\n')) > 3):
        return True
    else:
        return False
        