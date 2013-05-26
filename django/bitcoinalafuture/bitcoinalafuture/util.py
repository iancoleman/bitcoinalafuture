from django.utils.timezone import make_aware, utc, now
from django.conf import settings

from jsonrpc import ServiceProxy

import datetime
import decimal
import pickle
import time
import urllib




def price(price_val):
    try:
        #TODO prec != decimal places
        decimal_places = 5
        decimal.getcontext().prec = decimal_places
        decimal_price = decimal.Decimal(price_val)
        return decimal_price
    except:
        return None

def datetime_to_unix_time(dt):
    return time.mktime(dt.timetuple())+1e-6*dt.microsecond

def unix_time_to_datetime_utc(unix):
    return datetime.datetime.fromtimestamp(unix, utc)

def get_utc_time_now(offset_in_seconds=0):
    utc_now = now()
    utc_offset = utc_now + datetime.timedelta(0, offset_in_seconds)
    return utc_offset

def datetime_is_in_the_future(datetime_to_check, seconds_from_now=3600):
    return datetime_to_check - datetime.timedelta(0, seconds_from_now) > now()

def get_bitcoin_address(account_name):
    conn = ServiceProxy(settings.BITCOIN_RPC_URL)
    address = conn.getnewaddress(account_name)
    return address

def get_bitcoin_transactions(last_tx_id):
    conn = ServiceProxy(settings.BITCOIN_RPC_URL)
    transactions = []
    tx = get_transaction(conn, len(transactions))
    while(tx is not None and tx["txid"] != last_tx_id):
        transactions.append(tx)
        tx = get_transaction(conn, len(transactions))
    transactions.reverse()
    return transactions
    
def get_transaction(conn, tx_from):
    transactions = conn.listtransactions('*', 1, tx_from)
    if(len(transactions) > 0):
        return transactions[0]

def get_bitcoin_transaction_info(tx_id):
    conn = ServiceProxy(settings.BITCOIN_RPC_URL)
    transaction_info = conn.gettransaction(tx_id)
    return transaction_info

def make_bitcoin_payment(to_address, amount):
    amount_float = float(amount)
    conn = ServiceProxy(settings.BITCOIN_RPC_URL)
    conn.settxfee(0.0005) # Also see bitcoinalafuture/settings.py FEE
    tx_id = conn.sendtoaddress(to_address, amount_float)
    return tx_id

def get_wallet_balance():
    conn = ServiceProxy(settings.BITCOIN_RPC_URL)
    balance = conn.getbalance()
    return balance
    
def validate_bitcoin_address(address):
    conn = ServiceProxy(settings.BITCOIN_RPC_URL)
    isvalid = conn.validateaddress(address)["isvalid"]
    return isvalid
    

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
