
import os


for filename in os.listdir("data"):
    if filename[:12] == "time-series-":
        weather_hex = filename[12:-4]
        if not os.path.join("assumptions-hash",'weather-{}.json'.format(weather_hex)):
            print("assumptions for weather not found:",weather_hex)
    elif filename[:15] =="results-series-":
        results_hex = filename[14:-4]
        if not os.path.join("assumptions-hash",'results-{}.json'.format(results_hex)):
            print("assumptions for results not found:",results_hex)
    elif filename[:17] =="results-overview-":
        results_hex = filename[16:-4]
        if not os.path.join("assumptions-hash",'results-{}.json'.format(results_hex)):
            print("assumptions for results not found:",results_hex)
    else:
        pass
