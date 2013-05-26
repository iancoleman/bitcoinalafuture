from django.http import HttpResponse
from django.shortcuts import render_to_response, render, get_object_or_404
from django.template import RequestContext
from django.utils.translation import ugettext as _
from django.db.models import Count, Sum

from thefuture.models import Future_Price
from thefuture.models import Prediction
from thefuture.models import Received_Amount
from thefuture.models import Returned_Amount
from thefuture.models import Returned_Tx
from thefuture.models import Commission_Amount
from thefuture.models import Bitcoin_Price
from thefuture.models import Rate_Limit
from thefuture.models import Returned_Tx_To_Returned_Amount_Link

from thefuture.funcs import get_future_price_data

from thefuture.settings import FUTURE_WINDOW, FEE

import bitcoinalafuture.util as util

import datetime
import json
import random
import re



def home(request):
    lt_str = _("less than")
    gt_str = _("more than")

    template_params = {
        'lt_gt_select': "<select id='lt_gt_select' name='lt_gt_select'><option value='gt'>%s</option><option value='lt'>%s</option></select>" % (gt_str, lt_str),
        'price_input': "<input id='price' name='price' type='number' min='0'>",
        'time_input': "<input id='datetimepicker' name='datetimepicker' type='datetime'>",
        'winning_address': "<input id='winning_address' name='winning_address' type='text'>",
    }
    return render_to_response('home.html', template_params, context_instance=RequestContext(request))

   
def make_new_prediction(request):

    #Check for rate limiting if too many predictions
    max_allowable_predictions = 100
    ip = util.get_client_ip(request)
    Rate_Limit.objects.create(ip=ip, function='make_new_prediction')
    limit = Rate_Limit.objects.filter(ip=ip, function='make_new_prediction').count()
    if limit > max_allowable_predictions:
        error_text = _("Slow down <span class='notranslate'>Rainman</span> - you've made too many predictions in the last hour")
        return HttpResponse(error_text, mimetype="text/plain", status=429)    
    
    lt = request.POST["lt"] == "lt"
    
    price = util.price(request.POST["price"])
    if price is None:
        error_text = _("Invalid price")
        return HttpResponse(error_text, mimetype="text/plain", status=400)
        
    unix_date = float(request.POST["time_to_check"]) / 1e3
    utc_date = util.unix_time_to_datetime_utc(unix_date)
    if utc_date is None:
        error_text = _("Invalid date")
        return HttpResponse(error_text, mimetype="text/plain", status=400)
    if not utc_date.second == 0 and utc_date.microsecond == 0:
        error_text = _("Date must not include seconds")
        return HttpResponse(error_text, mimetype="text/plain", status=400)
    if not util.datetime_is_in_the_future(utc_date, FUTURE_WINDOW):
        error_text = _("Must be at least two hours into the future")
        return HttpResponse(error_text, mimetype="text/plain", status=400)

    return_address = request.POST["return_address"]
    if re.search("\W", return_address) is not None:
        error_text = _("Return address is invalid")
        return HttpResponse(error_text, mimetype="text/plain", status=400)
    return_address_is_valid = util.validate_bitcoin_address(return_address)
    if not return_address_is_valid:
        error_text = _("Return address is invalid")
        return HttpResponse(error_text, mimetype="text/plain", status=400)

    account_name = str(int(lt)) + "-" + str(price) + "-" + str(util.datetime_to_unix_time(utc_date)) + "-" + return_address
    receive_address = util.get_bitcoin_address(account_name)

    future_price = {
        "target_price": price,
        "time_to_match_price": utc_date,
        "time_window_closes": utc_date - datetime.timedelta(0, FUTURE_WINDOW)
        }
    existing_future_price_obj = Future_Price.objects.filter(**future_price)
    if existing_future_price_obj.count() > 0:
        future_price_obj = existing_future_price_obj[0]
    else:
        future_price_obj = Future_Price(**future_price)
        future_price_obj.save()

    new_prediction = {
        "future_price": future_price_obj,
        "receive_address": receive_address,
        "price_will_be_less_than_target": lt,
        "return_address": return_address,
        }
    prediction_obj = Prediction(**new_prediction)
    prediction_obj.save()
    
    response_data = {
        "address": receive_address
        }
    return HttpResponse(json.dumps(response_data), mimetype="application/json")


def the_future(request):

    #Check for rate limiting if too many requests
    max_allowable_requests = 3600
    ip = util.get_client_ip(request)
    Rate_Limit.objects.create(ip=ip, function='the_future')
    limit = Rate_Limit.objects.filter(ip=ip, function='the_future').count()
    if limit > max_allowable_requests:
        error_text = _("Slow down <span class='notranslate'>Rainman</span> - you've made too many requests in the last hour")
        return HttpResponse(error_text, mimetype="text/plain", status=429) 

    after = True
    if "after" in request.GET:
        time = util.unix_time_to_datetime_utc(float(request.GET["after"]) / 1e3)
    elif "before" in request.GET:
        time = util.unix_time_to_datetime_utc(float(request.GET["before"]) / 1e3)
        after=False
    else:
        time = util.get_utc_time_now()
    predictions_per_page = 10
    if after:
        future_price_times = Future_Price.objects.filter(time_to_match_price__gt=time).distinct('time_to_match_price').order_by('time_to_match_price')[0:predictions_per_page]
        future_prices = Future_Price.objects.filter(time_to_match_price__in=[x.time_to_match_price for x in future_price_times]).order_by('time_to_match_price', 'target_price')
    else:
        future_price_times = Future_Price.objects.filter(time_to_match_price__lt=time).distinct('time_to_match_price').order_by('-time_to_match_price')[0:predictions_per_page]
        future_prices = Future_Price.objects.filter(time_to_match_price__in=[x.time_to_match_price for x in future_price_times]).order_by('time_to_match_price', 'target_price')
    response_data = []
    for f in future_prices:
        received_amounts = Received_Amount.objects.filter(prediction__future_price=f)
        if len(received_amounts) > 0:
            expires = f.time_to_match_price.isoformat()
            prediction = {
                'id': f.id,
                'target_price': float(f.target_price),
                'deposits': [{
                    'amount': float(r.amount),
                    'lt': r.prediction.price_will_be_less_than_target,
                    'time_received': r.time.isoformat(),
                    'js_time_received': int(util.datetime_to_unix_time(r.time) * 1e3)
                    } for r in received_amounts]
                }
            if len(response_data) == 0 or response_data[-1]["expires"] != expires:
                response_data.append({
                    'expires': expires,
                    'js_expires': int(util.datetime_to_unix_time(f.time_to_match_price) * 1e3),
                    'predictions': [prediction]})
            else:
                response_data[-1]['predictions'].append(prediction)
                
    return HttpResponse(json.dumps(response_data), mimetype="application/json")

def future_price_detail_api(request, future_price_id, data_type):
    
    #Check for rate limiting if too many requests
    max_allowable_requests = 7200
    ip = util.get_client_ip(request)
    Rate_Limit.objects.create(ip=ip, function='future_price_detail')
    limit = Rate_Limit.objects.filter(ip=ip, function='future_price_detail').count()
    if limit > max_allowable_requests:
        error_text = _("Slow down <span class='notranslate'>Rainman</span> - you've made too many requests in the last hour")
        return HttpResponse(error_text, mimetype="text/plain", status=429)

    if data_type != "json":
        error_text = _("Invalid data type")
        return HttpResponse(error_text, mimetype="text/plain", status=400)
        
    f = get_object_or_404(Future_Price, id=future_price_id)
    future_price = get_future_price_data(f)
    return HttpResponse(json.dumps(future_price), mimetype="application/json")
    
def future_price_detail(request, future_price_id):

    #Check for rate limiting if too many requests
    max_allowable_requests = 7200
    ip = util.get_client_ip(request)
    Rate_Limit.objects.create(ip=ip, function='future_price_detail')
    limit = Rate_Limit.objects.filter(ip=ip, function='future_price_detail').count()
    if limit > max_allowable_requests:
        error_text = _("Slow down <span class='notranslate'>Rainman</span> - you've made too many requests in the last hour")
        return HttpResponse(error_text, mimetype="text/plain", status=429)

    f = get_object_or_404(Future_Price, id=future_price_id)
    future_price = get_future_price_data(f)
    return render_to_response("prediction_detail.html", future_price, context_instance=RequestContext(request))
    

def get_server_time(request):
    now = util.get_utc_time_now()
    response_data = {
        "server_time": util.datetime_to_unix_time(now) * 1e3,
        }        
    return HttpResponse(json.dumps(response_data), mimetype="application/json")



def statistics(request):

    #Check for rate limiting if too many requests
    max_allowable_requests = 3600
    ip = util.get_client_ip(request)
    Rate_Limit.objects.create(ip=ip, function='statistics')
    limit = Rate_Limit.objects.filter(ip=ip, function='statistics').count()
    if limit > max_allowable_requests:
        error_text = _("Slow down <span class='notranslate'>Rainman</span> - you've made too many requests in the last hour")
        return HttpResponse(error_text, mimetype="text/plain", status=429)

    total_received_transactions = Received_Amount.objects.count()
    total_unpaid_transactions = Returned_Amount.objects.filter(returned_tx_to_returned_amount_link__isnull=True).count() #TODO this must count only UNIQUE return addresses
    total_returned_transactions = Returned_Tx.objects.count()

    total_received_amount = Received_Amount.objects.aggregate(Sum('amount'))["amount__sum"]
    total_returned_amount_with_fees = Returned_Tx.objects.aggregate(Sum('returned_amount'))["returned_amount__sum"]
    total_fees_amount = Returned_Tx.objects.aggregate(Sum('fee'))["fee__sum"]
    total_pending_amount = Received_Amount.objects.filter(returned_amount__isnull=True).aggregate(Sum('amount'))["amount__sum"]
    total_unpaid_amount = Returned_Amount.objects.filter(returned_tx_to_returned_amount_link__isnull=True).aggregate(Sum('amount'))["amount__sum"]
    total_commission_amount = Commission_Amount.objects.aggregate(Sum('amount'))["amount__sum"]

    total_received_amount = total_received_amount if total_received_amount is not None else 0
    total_returned_amount_with_fees = total_returned_amount_with_fees if total_returned_amount_with_fees is not None else 0
    total_pending_amount = total_pending_amount if total_pending_amount is not None else 0
    total_unpaid_amount = total_unpaid_amount if total_unpaid_amount is not None else 0
    total_commission_amount = total_commission_amount if total_commission_amount is not None else 0
    total_fees_amount = total_fees_amount if total_fees_amount is not None else 0

    statistics = {
        'total_received_transactions': total_received_transactions,
        'total_unpaid_transactions': total_unpaid_transactions,
        'total_returned_transactions': total_returned_transactions,
        'total_received_amount': "%0.8f" % total_received_amount,
        'total_pending_amount': "%0.8f" % total_pending_amount,
        'total_unpaid_amount': "%0.8f" % total_unpaid_amount,
        'total_returned_amount_with_fees': "%0.8f" % total_returned_amount_with_fees,
        'total_commission_amount': "%0.8f" % total_commission_amount,
        'total_fees_amount': "%0.8f" % total_fees_amount,
        }
    return render_to_response('statistics.html', statistics, context_instance=RequestContext(request))

def address(request, address, data_type):

    #Check for rate limiting if too many requests
    max_allowable_requests = 3600
    ip = util.get_client_ip(request)
    Rate_Limit.objects.create(ip=ip, function='address')
    limit = Rate_Limit.objects.filter(ip=ip, function='address').count()
    if limit > max_allowable_requests:
        error_text = _("Slow down <span class='notranslate'>Rainman</span> - you've made too many requests in the last hour")
        return HttpResponse(error_text, mimetype="text/plain", status=429)

    if data_type != "json":
        error_text = _("Invalid data type")
        return HttpResponse(error_text, mimetype="text/plain", status=400)
    
    if re.search("\W", address) is not None:
        error_text = _("Address is invalid")
        return HttpResponse(error_text, mimetype="text/plain", status=400)
    address_is_valid = util.validate_bitcoin_address(address)
    if not address_is_valid:
        error_text = _("Address is invalid")
        return HttpResponse(error_text, mimetype="text/plain", status=400)

    response_data = {}

    received = Received_Amount.objects.filter(prediction__receive_address=address).aggregate(Sum('amount'))["amount__sum"]
    returned_pending = Returned_Amount.objects.filter(returned_tx_to_returned_amount_link__isnull=True, to_prediction__return_address=address).aggregate(Sum('amount'))["amount__sum"]
    returned = Returned_Amount.objects.filter(returned_tx_to_returned_amount_link__isnull=False, to_prediction__return_address=address).aggregate(Sum('amount'))["amount__sum"]
    
    response_data["received"] = float(received) if received is not None else 0
    response_data["returned_pending"] = float(returned_pending) if returned_pending is not None else 0
    response_data["returned"] = float(returned) if returned is not None else 0
    return HttpResponse(json.dumps(response_data), mimetype="application/json")


def api(request):
    return render_to_response('api.html', {}, context_instance=RequestContext(request))

def how_it_works(request):
    return render_to_response("how_it_works.html", {}, context_instance=RequestContext(request))

def contact(request):
    return render_to_response("contact.html", {}, context_instance=RequestContext(request))
    