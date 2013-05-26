import datetime
from decimal import *
import json
import time
import threading
import urllib
import websocket

from django.core.management.base import BaseCommand, CommandError
from django.utils.timezone import utc

from thefuture.models import BitcoinPrice
import bitcoinalafuture.util as util

DEPTH = "24e67e0d-1cad-4cc0-9e7a-f8523ef460fe"
TRADE = "dbf1dee9-4f2e-4a08-8cb7-748919a71b21"
TICKER = "d5f06780-30a8-4a48-a2f8-7ed181b4a13f"

class Command(BaseCommand):
    price_float = None
    price_int = None
    last_time_gox = None
    last_time_server = util.get_utc_time_now()
    ws = websocket.WebSocketApp("ws://websocket.mtgox.com/mtgox")
    
    def handle(self, *args, **options):
        #self.test()
        #websocket.enableTrace(True)
        self.get_initial_price()
        self.ws.on_message = self.on_message
        self.ws.on_error = self.on_error
        self.ws.on_close = self.on_close
        self.ws.on_open = self.on_open
        #self.get_rollover_price()
        while(True):
            try:
                self.ws.run_forever()
            except websocket.WebSockeError:
                print "EXCEPTION"
                time.sleep(5)
        
    def on_open(self, ws):
        print("%s websocket open" % util.get_utc_time_now().isoformat())
        self.ws.send(json.dumps({
            "op": "unsubscribe",
            "channel": TICKER}))
        self.ws.send(json.dumps({
            "op": "unsubscribe",
            "channel": DEPTH}))
        self.ws.send(json.dumps({
            "op": "subscribe",
            "channel": TRADE}))

    def on_message(self, ws, message):
        new_msg_time_server = util.get_utc_time_now()
        msg = json.loads(message)
        trade = msg["trade"]
        if(trade["price_currency"] == "USD"):
            self.handle_trade(trade, new_msg_time_server, "socket")

    def on_error(self, ws, error):
        print("%s ERROR - %s" % (util.get_utc_time_now(), error))

    def on_close(self, ws):
        print("%s websocket closed" % util.get_utc_time_now().isoformat())

    def handle_trade(self, trade, new_msg_time_server, source):
        new_msg_time_gox = util.unix_time_to_datetime_utc(trade["date"])
        if(self.last_time_gox is not None):
            tickovers = util.get_clear_minutes(self.last_time_gox, new_msg_time_gox)
            # Set those minutes to the last price
            for tickover in tickovers:
                print("%s %f SAVING" % (tickover.isoformat(), self.price_float))
                new_bitcoin_price = {
                    'time': tickover,
                    'price': self.price_float,
                    }
                bitcoin_price = BitcoinPrice(**new_bitcoin_price)
                bitcoin_price.save()
        if source == "socket":
            self.price_float = trade["price"]
            self.price_int = trade["price_int"]
            self.last_time_server = new_msg_time_server
            self.last_time_gox = new_msg_time_gox
        print("%s %f %s" % (new_msg_time_gox.isoformat(), self.price_float, source))



    def get_initial_price(self):
        one_hour = datetime.timedelta(0,3600,0)
        time_of_interest = util.get_utc_time_now() - one_hour
        unix_time_of_interest = util.datetime_to_unix_time(time_of_interest) * 1e6
        url = "https://mtgox.com/api/1/BTCUSD/trades?since=%i" % unix_time_of_interest
        f = urllib.urlopen(url)
        trades_json = f.read()
        trades = json.loads(trades_json)["return"]
        last_trade = trades[-1]
        self.price_float = float(last_trade["price"])
        self.price_int = float(last_trade["price_int"])
        self.last_time_gox = util.unix_time_to_datetime_utc(last_trade["date"])
        print("INITIAL PRICE: %f" % (self.price_float))

        """
    def get_rollover_price(self):
        # When a clear minute is encountered, simulate a socket message using
        # the current price, so that long periods between socket messages do
        # not mean the database lags far behind. Without this, the database
        # is only written when websocket messages arrive, which can be many
        # minutes apart.
        now_server = util.get_utc_time_now()
        now_gox = self.get_gox_time_from_server_time(now_server)
        if now_gox is not None:
            rollover_trade = {
                "price": self.price_float,
                "price_int": self.price_int,
                "date": util.datetime_to_unix_time(now_gox)
            }
            self.handle_trade(rollover_trade, now_server, "rollover")
            # future event should happen at least one second after rollover to
            # account for errors due to no milliseconds on the gox time.
            # Worst case error is when we calculate the gox time 0.999999 second
            # wrong.
            now_gox = self.get_gox_time_from_server_time(now_server)
            future_event = datetime.datetime(now_gox.year, now_gox.month, now_gox.day, now_gox.hour, now_gox.minute, 0, 0, utc) + datetime.timedelta(0, 60, 0)
            period_to_sleep = future_event - now_gox
        else:
            now_server = util.get_utc_time_now()
            future_event = datetime.datetime(now_server.year, now_server.month, now_server.day, now_server.hour, now_server.minute, 0, 0, utc) + datetime.timedelta(0, 60, 0)
            period_to_sleep = future_event - now_server
        t = threading.Timer(period_to_sleep.total_seconds(), self.get_rollover_price)
        t.daemon = True
        t.start()
        """

    def get_gox_time_from_server_time(self, dt):
        if(self.last_time_gox is not None):
            return dt - self.last_time_server + self.last_time_gox

    def get_time_from_message(self, msg):
        return datetime.datetime.fromtimestamp(msg["trade"]["date"], utc)


        