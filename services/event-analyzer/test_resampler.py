import urllib.request
try:
    urllib.request.urlopen("https://pypi.org/pypi/plotly-resampler/json", timeout=2)
    print("Internet access OK")
except Exception as e:
    print("No internet:", e)
