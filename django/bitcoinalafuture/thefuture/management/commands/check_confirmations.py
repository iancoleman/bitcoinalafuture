from django.core.management.base import BaseCommand, CommandError

from thefuture.models import Received_Amount
import bitcoinalafuture.util as util

import datetime
import subprocess

class Command(BaseCommand):
    def handle(self, *args, **options):
        if already_running():
            #self.stdout.write("Already running")
            return
        fifty_minutes_ago = util.get_utc_time_now() - datetime.timedelta(0,50*60)
        unconfirmed_received_amounts = Received_Amount.objects.filter(confirmations__lt=6, time__lt=fifty_minutes_ago)
        for unconfirmed_amount in unconfirmed_received_amounts:
            tx_info = util.get_bitcoin_transaction_info(unconfirmed_amount.tx_id)
            if tx_info["confirmations"] >= 6:
                if tx_info["amount"] != unconfirmed_amount.amount:
                    #TODO log this, it is very interesting, reversed transaction
                    pass
                unconfirmed_amount.confirmations = tx_info["confirmations"]
                unconfirmed_amount.amount = tx_info["amount"]
                unconfirmed_amount.save()

def already_running():
    pid = subprocess.Popen(["ps -ef | grep clear_ips | grep -v grep", ""], stdout=subprocess.PIPE, shell=True).stdout.read()
    if(len(pid.split('\n')) > 3):
        return True
    else:
        return False