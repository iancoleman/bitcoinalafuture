from django.core.management.base import BaseCommand, CommandError

from thefuture.funcs import get_unresolved_future_prices, evaluate_winners_and_losers, evaluate_amounts_received_after_window_closes

import bitcoinalafuture.util as util

import subprocess

"""
Gets all the unresolved predictions that can be resolved given the current
bitcoin price information, and works out who gets paid what.
"""

class Command(BaseCommand):
    def handle(self, *args, **options):
        if already_running():
            #self.stdout.write("Already running")
            return
        future_prices = get_unresolved_future_prices()
        for future_price in future_prices:
            evaluate_winners_and_losers(future_price)
        evaluate_amounts_received_after_window_closes()

def already_running():
    pid = subprocess.Popen(["ps -ef | grep find_the_past | grep -v grep", ""], stdout=subprocess.PIPE, shell=True).stdout.read()
    if(len(pid.split('\n')) > 3):
        return True
    else:
        return False