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
        wait_period = 2 #seconds between checks of the alarms
        if already_running():
            #self.stdout.write("Already running")
            return
        time_now = util.get_utc_time_now()
        while (time_now.second < 55):
            check_ssh_log_for_bad_entries()
            check_bitcoind_is_running()
            check_hdd_space()
            check_price_is_not_far_behind()
            check_cpu_and_ram_state()
            check_for_missing_prices()
            check_bitcoin_conf()
            time.sleep(wait_period)
            time_now = util.get_utc_time_now()


def raise_alarm(text):
    pass

def check_ssh_log_for_bad_entries():
    pass

def check_bitcoind_is_running():
    pass

def check_hdd_space():
    pass

def check_price_is_not_far_behind():
    pass

def check_cpu_and_ram_state():
    pass

def check_for_missing_prices():
    pass

def check_bitcoin_conf():
    pass
            
def already_running():
    pid = subprocess.Popen(["ps -ef | grep alarms | grep -v grep", ""], stdout=subprocess.PIPE, shell=True).stdout.read()
    if(len(pid.split('\n')) > 3):
        return True
    else:
        return False