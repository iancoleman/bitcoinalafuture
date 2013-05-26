import datetime
import json
import urllib
import subprocess
import time

from django.core.management.base import BaseCommand, CommandError

from thefuture.models import Bitcoin_Price
from thefuture.funcs import get_clear_minutes, find_clear_minute_prices

import bitcoinalafuture.util as util

class Command(BaseCommand):
    def handle(self, *args, **options):
        if already_running():
            #self.stdout.write("Already running")
            return
        time_started = util.get_utc_time_now()
        has_expired = False
        now = util.get_utc_time_now()
        one_hour = datetime.timedelta(0, 3600, 0)
        try:
            last_bitcoin_price = Bitcoin_Price.objects.order_by('-time')[0]
            last_tid = last_bitcoin_price.rollover_id_b
        except IndexError:
            last_tid = int(util.datetime_to_unix_time(now-one_hour) * 1e6)
        trades = self.get_gox_trades(last_tid - 1) # needs to include the last rollover trade
        if len(trades) > 0:
            try:
                last_tid = int(trades[0]["tid"])
            except:
                return
            last_price = trades[0]["price"]
        while (len(trades) > 0 and not has_expired):
            prices = find_clear_minute_prices(trades, last_tid, last_price)
            for price in prices:
                bitcoin_price = Bitcoin_Price(**price)
                bitcoin_price.save()
            last_tid = int(trades[-1]["tid"])
            last_price = trades[-1]["price"]
            
            time.sleep(1) # Don't hammer the gox server too hard
            time_taken = util.get_utc_time_now() - time_started
            has_expired = time_taken.total_seconds() > 30
            # Check if there are more trades after the last trade in the
            # previous set of trades
            if (len(trades) == 500):
                trades = self.get_gox_trades(last_tid)
            else:
                trades = []

    def get_gox_trades(self, last_tid):
        try:
            url = "https://mtgox.com/api/1/BTCUSD/trades?since=%i" % last_tid
            f = urllib.urlopen(url)
            trades_json = f.read()
            trades = json.loads(trades_json)
            if trades["result"] == "success":
                return trades["return"]
        except:
            pass
        return json.dumps([])
            



def already_running():
    pid = subprocess.Popen(["ps -ef | grep update_bitcoin_rate | grep -v grep", ""], stdout=subprocess.PIPE, shell=True).stdout.read()
    if(len(pid.split('\n')) > 3):
        return True
    else:
        return False