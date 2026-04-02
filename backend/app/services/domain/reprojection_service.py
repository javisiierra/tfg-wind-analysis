import geopandas as gpd


def ensure_25830_crs(gdf):
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=25830)
    elif gdf.crs.to_epsg() != 25830:
        gdf = gdf.to_crs(epsg=25830)

    return gdf