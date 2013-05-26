import decimal

decimal.getcontext().prec = 8

FUTURE_WINDOW = 2*60*60 # prediction must be at least X seconds into the future
COMMISSION = decimal.Decimal(0.1)
COMMISSION_ADDRESS = "mu3aC2gRYteoEbBN5JGoFyiTnutTLQsHY7"
COLD_STORAGE_ADDRESS = "n2wcG1PAtt22MJsh3DQzZzqdMpB3ww3CNR"
FEE = decimal.Decimal(0.0005) # Also see coinman/make_payment.py settxfee
DATETIME_FORMAT = "%Y-%m-%d %H:%M"