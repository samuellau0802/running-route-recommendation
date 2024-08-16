import pandas as pd
import polyline
import pydeck as pdk

def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def format_output_route(route_finder):
    df = pd.DataFrame()
    route = polyline.decode(route_finder.result_route.polyline)
    df["path"] = [[[i[1], i[0]] for i in route]]
    df["color"] = ["#ed1c24"]
    df['color'] = df['color'].apply(hex_to_rgb)

    view_state = pdk.ViewState(
        latitude=route_finder.init_cor[0],
        longitude=route_finder.init_cor[1],
        zoom=13
    )
    layer = pdk.Layer(
        type='PathLayer',
        data=df,
        pickable=True,
        get_color='color',
        width_scale=10,
        width_min_pixels=2,
        get_path='path',
        get_width=2
    )

    return view_state, layer