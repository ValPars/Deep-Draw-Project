import pandas as pd
from PIL import Image
import streamlit as st
from streamlit_drawable_canvas import st_canvas
import json
from deep_draw.dl_logic.utils import vector_to_raster, raw_to_lines, lines_to_strokes, to_big_strokes, clean_strokes, to_normal_strokes, strokes_to_lines, stroke_to_quickdraw, image_to_dict
import numpy as np
from tensorflow import keras
import matplotlib.pyplot as plt
from rdp import rdp
import random
import io
import requests
from json import JSONEncoder


# Create a canvas component
st.set_page_config(page_title="Deep Draw", page_icon="🎨")
st.header("Dessine-moi un mouton")

canvas_result = st_canvas(
    fill_color="rgba(255, 165, 0, 0.3)",  # Fixed fill color with some opacity
    stroke_width=1,
    stroke_color="#000",
    background_color="#eee",
    background_image=None,
    update_streamlit=True,
    #height=600,
    drawing_mode="freedraw",
    point_display_radius=0,
    key="canvas",
)
try:
    if canvas_result.json_data is not None:

        objects = pd.json_normalize(canvas_result.json_data["objects"])

        path = []
        for i in range(len(objects["path"])):
            path.append(list(objects["path"][i][1:-1]))

        quickdraw_format = []
        for i in range(len(path)):
            x = [point[1] for point in path[i]]
            y = [point[2] for point in path[i]]
            quickdraw_format.append([x, y])

        ndjson_format = {}
        ndjson_format["drawing"] = quickdraw_format
        ndjson_format["word"] = "Live drawing"
        ndjson_format["key_id"] = "1"
        ndjson_format["countrycode"] = "FR"

        #Step 1
        raw_lines = raw_to_lines(quickdraw_format)
        raw_strokes_3 = lines_to_strokes(raw_lines, delta=False)

        # Step 2
        raw_strokes_3 = to_big_strokes(raw_strokes_3, max_len=5000)
        raw_strokes_3 = np.array(clean_strokes(raw_strokes_3, factor=1))
        raw_strokes_3 = to_normal_strokes(raw_strokes_3)

        # Steps 3&4
        lower = np.min(raw_strokes_3[:, 0:2], axis=0)
        upper = np.max(raw_strokes_3[:, 0:2], axis=0)
        scale = upper - lower
        scale[scale == 0] = 1
        raw_strokes_3[:, 0:2] = (raw_strokes_3[:, 0:2] - lower)*255 / scale

        # Step 5
        raw_strokes_3[1:, 0:2] -= raw_strokes_3[:-1, 0:2]

        # Step 6
        lines = strokes_to_lines(raw_strokes_3)
        simp_lines = []
        N = len(lines)
        for i in range(N):
            line = rdp(lines[i], epsilon=2)
            simp_lines.append(line)

        # Step 7
        simp_strokes_3 = lines_to_strokes(simp_lines, delta=True)
        simp_strokes_3 = np.round(simp_strokes_3).astype(float)
        strokes = stroke_to_quickdraw(simp_strokes_3, max_dim_size=255)

        #we have now 'quickdraw_format' as the path and 'bitmap_format' for the bitmap
        bitmap_format = np.array(vector_to_raster([strokes], side=28)).reshape(1, 28, 28, 1)
        json_to_api = image_to_dict(bitmap_format)
        json_to_api_2 = json.dumps(json_to_api)
        #url = 'https://deepdrawimage-do5ciztupa-ew.a.run.app/predict/'
        url = 'http://127.0.0.1:8000/predict'
        if st.button('submit'):
            with requests.Session() as s:
                response = s.post(url, json_to_api_2)
            st.markdown("""
                <style>
                .big-font {
                    font-size:35px !important;
                }
                </style>
                """, unsafe_allow_html=True)

            st.markdown(f"<p class='big-font'>{response.json()['test'].title()}   </p>", unsafe_allow_html=True)

except:
    pass
