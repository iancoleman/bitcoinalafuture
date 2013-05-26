from django.core.management.base import BaseCommand, CommandError

from thefuture.models import Rate_Limit
import bitcoinalafuture.util as util

import datetime
import subprocess

class Command(BaseCommand):
    def handle(self, *args, **options):
        if already_running():
            #self.stdout.write("Already running")
            return
        one_hour_ago = util.get_utc_time_now() - datetime.timedelta(0, 3600)
        Rate_Limit.objects.filter(time__lt=one_hour_ago).delete()


def already_running():
    pid = subprocess.Popen(["ps -ef | grep clear_ips | grep -v grep", ""], stdout=subprocess.PIPE, shell=True).stdout.read()
    if(len(pid.split('\n')) > 3):
        return True
    else:
        return False