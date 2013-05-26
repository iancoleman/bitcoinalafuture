import datetime
import time
import subprocess

from django.core.management.base import BaseCommand, CommandError
from django.utils.timezone import make_aware, utc

from thefuture.models import Received_Amount, Prediction

import bitcoinalafuture.util as util

class Command(BaseCommand):
    def handle(self, *args, **options):
        wait_period = 2 #seconds between checks of the deposits
        if already_running():
            #self.stdout.write(datetime.datetime.now().isoformat() + " check_deposits is already running\n")
            return
        try:
            last_received_amount = Received_Amount.objects.order_by('-time')[0]
            last_tx_id = last_received_amount.tx_id
        except: #IndexError:
            last_tx_id = None
        #self.stdout.write("started\n")
        time_now = util.get_utc_time_now()
        while (time_now.second < 55):
            new_transactions = util.get_bitcoin_transactions(last_tx_id)
            #self.stdout.write("New txs: %i\n" % len(new_transactions))
            for new_tx in new_transactions:
                try:
                    amount = new_tx["amount"]
                except TypeError:
                    print "TYPERROR!!!!: %s" % new_tx
                    print new_tx["amount"]
                if(new_tx["amount"] > 0):
                    tx = {
                        "tx_id": new_tx["txid"],
                    }
                    num_existing_transaction_entries = Received_Amount.objects.filter(**tx).count()
                    predictions = Prediction.objects.filter(receive_address=new_tx["address"])
                    if(num_existing_transaction_entries == 0 and predictions.count() == 1):
                        tx["prediction"] = predictions[0]
                        tx["amount"] = new_tx["amount"]
                        tx["time"] = util.unix_time_to_datetime_utc(new_tx["time"])
                        new_payment_obj = Received_Amount(**tx)
                        new_payment_obj.save()
                    elif last_tx_id is not None:
                        pass
                        #TODO raise some better notice, something has gone wrong, should never count the same tx twice.
            if(len(new_transactions) > 0):
                last_tx_id = new_transactions[-1]["txid"]
            #self.stdout.write(last_tx_id + "\n")
            time.sleep(wait_period)
            time_now = util.get_utc_time_now()

def already_running():
    pid = subprocess.Popen(["ps -ef | grep watch_wallet | grep -v grep", ""], stdout=subprocess.PIPE, shell=True).stdout.read()
    if(len(pid.split('\n')) > 3):
        return True
    else:
        return False

    