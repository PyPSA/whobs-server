
import xarray as xr



cutout_dir = "/beegfs/work/ws/ka_kc5996-cutouts-0/"

year = 2014

for i in range(8):

    cutout_name = "octant{}-{}".format(i, year)
    print("Processing",cutout_name)

    for tech in ["onwind","solar"]:

        ds = xr.open_dataset("{}{}-{}.nc".format(cutout_dir, cutout_name, tech))

        for stat in ["mean","max"]:
            getattr(ds,stat)(dim="time").to_dataframe().to_csv("{}-{}-{}.csv".format(cutout_name,tech,stat))

        ds_monthly = ds.resample(time="MS").mean(dim="time")
        ratio = ds_monthly.__xarray_dataarray_variable__.loc["{}-07-01".format(year),:]/ds_monthly.__xarray_dataarray_variable__.loc["{}-01-01".format(year),:]
        ratio.to_dataframe().to_csv("{}-{}-seasonal-jul_over_jan.csv".format(cutout_name,tech))
