from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

class Future_Price(models.Model):
    target_price = models.DecimalField(max_digits=15, decimal_places=5)
    time_to_match_price = models.DateTimeField()
    time_window_closes = models.DateTimeField()
    currency_code = models.CharField(max_length=3, default="USD")
    exchange = models.CharField(max_length=30, default="Mt Gox")
    time_created = models.DateTimeField(auto_now_add=True)

class Prediction(models.Model):
    future_price = models.ForeignKey(Future_Price)
    receive_address = models.CharField(max_length=34)
    return_address = models.CharField(max_length=34)
    price_will_be_less_than_target = models.BooleanField()
    time_created = models.DateTimeField(auto_now_add=True)
    def __unicode__(self):
        return self.receive_address

class Received_Amount(models.Model):
    prediction = models.ForeignKey(Prediction)
    amount = models.DecimalField(max_digits=15, decimal_places=8, default=0)
    time = models.DateTimeField()
    tx_id = models.CharField(max_length=64)
    confirmations = models.IntegerField(default=0)
    in_cold_storage = models.BooleanField(default=False)

class Returned_Amount(models.Model):
    amount = models.DecimalField(max_digits=15, decimal_places=8)
    from_received_amount = models.ForeignKey(Received_Amount)
    to_prediction = models.ForeignKey(Prediction)
    time_created = models.DateTimeField(auto_now_add=True)

class Returned_Tx(models.Model):
    returned_amount = models.DecimalField(max_digits=15, decimal_places=8)
    time_returned = models.DateTimeField(auto_now_add=True)
    tx_id = models.CharField(max_length=64)
    fee = models.DecimalField(max_digits=15, decimal_places=8)

class Returned_Tx_To_Returned_Amount_Link(models.Model):
    returned_tx = models.ForeignKey(Returned_Tx)
    returned_amount = models.ForeignKey(Returned_Amount)

class Commission_Amount(models.Model):
    returned_amount = models.ForeignKey(Returned_Amount)
    amount = models.DecimalField(max_digits=15, decimal_places=8)

class Commission_Tx(models.Model):
    amount = models.DecimalField(max_digits=15, decimal_places=8)
    tx_id = models.CharField(max_length=64)
    fee = models.DecimalField(max_digits=15, decimal_places=8)

class Commission_Tx_Link(models.Model):
    commission_amount = models.ForeignKey(Commission_Amount)
    commission_tx = models.ForeignKey(Commission_Tx)

class Bitcoin_Price(models.Model):
    time = models.DateTimeField(unique=True)
    price = models.DecimalField(max_digits=15, decimal_places=5)
    currency_code = models.CharField(max_length=3, default="USD")
    exchange = models.CharField(max_length=30, default="Mt Gox")
    rollover_id_a = models.BigIntegerField()
    rollover_id_b = models.BigIntegerField()

class Rate_Limit(models.Model):
    function = models.CharField(max_length=40)
    ip = models.CharField(max_length=16)
    time = models.DateTimeField(auto_now_add=True)


