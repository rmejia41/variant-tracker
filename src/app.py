import dash
from dash import dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
from sodapy import Socrata
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

# Load environment variables
load_dotenv()

# Constants
DATA_URL = 'data.cdc.gov'
DATA_SET = 'jr58-6ysp'
APP_TOKEN = os.getenv('SOCRATA_APP_TOKEN')
MODERN_BLUE_COLOR = "#007BFF"
RED_COLOR = "#FF0000"
DARK_BLUE_COLOR = "#00008B"

# Log environment variables
logging.info(f"APP_TOKEN: {APP_TOKEN}")

# Check for environment variables
if not APP_TOKEN:
    raise ValueError("Socrata App Token not set in the environment variables.")

# Function Definitions
def fetch_data(data_url, data_set, app_token):
    logging.info(f"Fetching data from {data_url} with dataset {data_set}")
    client = Socrata(data_url, app_token)
    client.timeout = 90
    results = client.get(data_set, limit=1500000)
    logging.info(f"Data fetched: {len(results)} records")
    return pd.DataFrame.from_records(results)

def preprocess_data(df):
    logging.info("Preprocessing data")
    df['week_ending'] = pd.to_datetime(df['week_ending'])
    df['creation_date'] = pd.to_datetime(df['creation_date'])
    df['share'] = df['share'].astype(float)
    return df

def get_default_date_range():
    logging.info("Getting default date range")
    end_date = datetime.today().date()
    start_date = end_date - timedelta(days=15)
    return start_date, end_date

# Fetch and preprocess data
logging.info("Starting data fetch and preprocess")
df = fetch_data(DATA_URL, DATA_SET, APP_TOKEN)
df = preprocess_data(df)
latest_published_date = df['creation_date'].max().strftime('%B %d, 2023')
start_date_default, end_date_default = get_default_date_range()
logging.info(f"Latest published date: {latest_published_date}")

# Initialize Dash app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])
server = app.server

# Define app layout
app.layout = dbc.Container(fluid=True, children=[
    dcc.Store(id='filtered-data'),
    dcc.Store(id='date-range-store', data={'start_date': str(start_date_default), 'end_date': str(end_date_default)}),
    dbc.Row(justify="center", children=[
        dbc.Col(md=8, children=[
            html.H1("SARS-CoV-2 Variant Tracker", className="mb-2 mt-2 text-center", style={'color': MODERN_BLUE_COLOR}),
            html.P("Visualize the distribution of variant proportions over time.", className="mb-2 text-center", style={'color': MODERN_BLUE_COLOR}),
            html.P(f"Latest CDC Data Update: {latest_published_date}", className="mb-4 text-center", style={'color': RED_COLOR}),
        ])
    ]),
    dbc.Row([
        dbc.Col(md=4, children=[
            html.Div([
                html.Label("Select Date Range:", className="form-label"),
                dcc.DatePickerRange(
                    id='date-picker-range',
                    start_date=start_date_default,
                    end_date=end_date_default,
                    min_date_allowed=df['week_ending'].min().date(),
                    max_date_allowed=df['week_ending'].max().date(),
                    className="mb-4"
                ),
                dbc.Row([
                    dbc.Col(html.Button('Reset Date Range', id='reset-date-range', n_clicks=0, className="btn btn-primary mb-4"), width={"size": 6, "offset": 3}),
                ]),
                html.Div(style={'height': '10px'}),
                html.Label("Select Variant:", className="form-label"),
                dcc.Dropdown(
                    id='variant-selector',
                    options=[{'label': 'All Variants', 'value': 'ALL'}] +
                            [{'label': variant, 'value': variant} for variant in df['variant'].unique()],
                    value='ALL',
                    multi=True,
                    className="mb-4",
                    style={'color': DARK_BLUE_COLOR}
                ),
                html.Div(style={'height': '10px'}),
                html.Label("Select Graph Type:", className="form-label"),
                dcc.Dropdown(
                    id='graph-type-selector',
                    options=[
                        {'label': 'Box Plot', 'value': 'box'},
                        {'label': 'Bar Plot', 'value': 'bar'}
                    ],
                    value='bar',
                    className="mb-4",
                    style={'color': DARK_BLUE_COLOR}
                ),
            ], className="mb-5"),
        ]),
        dbc.Col(md=8, children=[
            dcc.Graph(id='variant-distribution'),
            html.Div([
                html.A("CDC Monitoring Variant Proportions",
                       href="https://covid.cdc.gov/covid-data-tracker/#variant-proportions",
                       target="_blank",
                       className="text-center d-block mt-4", style={'color': MODERN_BLUE_COLOR})
            ], className="text-center")
        ]),
    ])
])

# Define callbacks
@app.callback(
    [Output('date-picker-range', 'start_date'),
     Output('date-picker-range', 'end_date'),
     Output('graph-type-selector', 'value')],
    Input('reset-date-range', 'n_clicks')
)
def reset_date_range(n_clicks):
    logging.info(f"Reset date range button clicked {n_clicks} times")
    if n_clicks > 0:
        return str(start_date_default), str(end_date_default), 'bar'
    return dash.no_update, dash.no_update, dash.no_update

@app.callback(
    Output('filtered-data', 'data'),
    [Input('date-picker-range', 'start_date'),
     Input('date-picker-range', 'end_date'),
     Input('variant-selector', 'value')])
def filter_data(start_date, end_date, selected_variants):
    logging.info(f"Filtering data for date range: {start_date} to {end_date} and variants: {selected_variants}")
    start_date = pd.to_datetime(start_date).date()
    end_date = pd.to_datetime(end_date).date()

    filtered_df = df.copy()

    if 'ALL' not in selected_variants and selected_variants is not None and len(selected_variants) > 0:
        filtered_df = filtered_df[filtered_df['variant'].isin(selected_variants)]

    filtered_df = filtered_df[
        (filtered_df['week_ending'].dt.date >= start_date) &
        (filtered_df['week_ending'].dt.date <= end_date)
    ]

    filtered_df['share'] = filtered_df['share'] * 100
    logging.info(f"Filtered data size: {filtered_df.shape}")
    return filtered_df.to_dict('records')

@app.callback(
    Output('variant-distribution', 'figure'),
    [Input('filtered-data', 'data'),
     Input('graph-type-selector', 'value')])
def update_graph(filtered_data, graph_type):
    logging.info(f"Updating graph with graph type: {graph_type}")
    filtered_df = pd.DataFrame(filtered_data)

    if filtered_df.empty or 'variant' not in filtered_df.columns:
        logging.warning("No data available for the selected criteria.")
        return px.scatter(title="No data available for the selected criteria.")

    if graph_type == 'box':
        fig = px.box(filtered_df, x='variant', y='share',
                     title="Distribution of SARS-CoV-2 Variant Proportions",
                     labels={'share': 'Variant Proportion (%)', 'variant': 'Variant'},
                     color='variant', notched=False)
        fig.update_traces(hovertemplate='<b>%{x}</b><br>Proportion: %{y:.2f}%<extra></extra>')
    elif graph_type == 'bar':
        filtered_df = filtered_df.groupby('variant', as_index=False).agg({'share': 'mean'})
        fig = px.bar(filtered_df, x='variant', y='share',
                     title="Proportions of SARS-CoV-2 Variants",
                     labels={'share': 'Variant Proportion (%)', 'variant': 'Variant'},
                     color='variant')
        fig.update_layout(xaxis={'categoryorder': 'total descending'})

    fig.update_layout(transition_duration=500)
    return fig

# Run the app
if __name__ == '__main__':
    app.run_server(debug=False)


# import dash
# from dash import dcc, html, Input, Output
# import dash_bootstrap_components as dbc
# import plotly.express as px
# import pandas as pd
# from sodapy import Socrata
# from datetime import datetime, timedelta
# from dotenv import load_dotenv
# import os
#
# # Load environment variables
# load_dotenv()
#
# # Constants
# DATA_URL = 'data.cdc.gov'
# DATA_SET = 'jr58-6ysp'
# APP_TOKEN = os.getenv('SOCRATA_APP_TOKEN')
# MODERN_BLUE_COLOR = "#007BFF"
# RED_COLOR = "#FF0000"
# DARK_BLUE_COLOR = "#00008B"
#
# # Check for environment variables
# if not APP_TOKEN:
#     raise ValueError("Socrata App Token not set in the environment variables.")
#
# # Function Definitions
# def fetch_data(data_url, data_set, app_token):
#     client = Socrata(data_url, app_token)
#     client.timeout = 90
#     results = client.get(data_set, limit=1500000)
#     return pd.DataFrame.from_records(results)
#
# def preprocess_data(df):
#     df['week_ending'] = pd.to_datetime(df['week_ending'])
#     df['creation_date'] = pd.to_datetime(df['creation_date'])
#     df['share'] = df['share'].astype(float)
#     return df
#
# def get_default_date_range():
#     end_date = datetime.today().date()
#     start_date = end_date - timedelta(days=15)
#     return start_date, end_date
#
# # Fetch and preprocess data
# df = fetch_data(DATA_URL, DATA_SET, APP_TOKEN)
# df = preprocess_data(df)
# latest_published_date = df['creation_date'].max().strftime('%B %d, 2023')
# start_date_default, end_date_default = get_default_date_range()
#
# # Initialize Dash app
# app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY]) # Using the DARKLY theme
# server = app.server  # Ensure this line is present
#
# # Define app layout
# app.layout = dbc.Container(fluid=True, children=[
#     dcc.Store(id='filtered-data'),
#     dcc.Store(id='date-range-store', data={'start_date': str(start_date_default), 'end_date': str(end_date_default)}),
#     dbc.Row(justify="center", children=[
#         dbc.Col(md=8, children=[
#             html.H1("SARS-CoV-2 Variant Tracker", className="mb-2 mt-2 text-center", style={'color': MODERN_BLUE_COLOR}),
#             html.P("Visualize the distribution of variant proportions over time.", className="mb-2 text-center", style={'color': MODERN_BLUE_COLOR}),
#             html.P(f"Latest CDC Data Update: {latest_published_date}", className="mb-4 text-center", style={'color': RED_COLOR}),
#         ])
#     ]),
#     dbc.Row([
#         dbc.Col(md=4, children=[
#             html.Div([
#                 html.Label("Select Date Range:", className="form-label"),
#                 dcc.DatePickerRange(
#                     id='date-picker-range',
#                     start_date=start_date_default,
#                     end_date=end_date_default,
#                     min_date_allowed=df['week_ending'].min().date(),
#                     max_date_allowed=df['week_ending'].max().date(),
#                     className="mb-4"
#                 ),
#                 dbc.Row([
#                     dbc.Col(html.Button('Reset Date Range', id='reset-date-range', n_clicks=0, className="btn btn-primary mb-4"), width={"size": 6, "offset": 3}),
#                 ]),
#                 html.Div(style={'height': '10px'}),
#                 html.Label("Select Variant:", className="form-label"),
#                 dcc.Dropdown(
#                     id='variant-selector',
#                     options=[{'label': 'All Variants', 'value': 'ALL'}] +
#                             [{'label': variant, 'value': variant} for variant in df['variant'].unique()],
#                     value='ALL',
#                     multi=True,
#                     className="mb-4",
#                     style={'color': DARK_BLUE_COLOR}
#                 ),
#                 html.Div(style={'height': '10px'}),
#                 html.Label("Select Graph Type:", className="form-label"),
#                 dcc.Dropdown(
#                     id='graph-type-selector',
#                     options=[
#                         {'label': 'Box Plot', 'value': 'box'},
#                         {'label': 'Bar Plot', 'value': 'bar'}
#                     ],
#                     value='bar',  # Set the default to 'bar'
#                     className="mb-4",
#                     style={'color': DARK_BLUE_COLOR}
#                 ),
#             ], className="mb-5"),
#         ]),
#         dbc.Col(md=8, children=[
#             dcc.Graph(id='variant-distribution'),
#             html.Div([
#                 html.A("CDC Monitoring Variant Proportions",
#                        href="https://covid.cdc.gov/covid-data-tracker/#variant-proportions",
#                        target="_blank",
#                        className="text-center d-block mt-4", style={'color': MODERN_BLUE_COLOR})
#             ], className="text-center")
#         ]),
#     ])
# ])
#
# # Define callbacks
# @app.callback(
#     [Output('date-picker-range', 'start_date'),
#      Output('date-picker-range', 'end_date'),
#      Output('graph-type-selector', 'value')],
#     Input('reset-date-range', 'n_clicks')
# )
# def reset_date_range(n_clicks):
#     if n_clicks > 0:
#         return str(start_date_default), str(end_date_default), 'bar'
#     return dash.no_update, dash.no_update, dash.no_update
#
# @app.callback(
#     Output('filtered-data', 'data'),
#     [Input('date-picker-range', 'start_date'),
#      Input('date-picker-range', 'end_date'),
#      Input('variant-selector', 'value')])
# def filter_data(start_date, end_date, selected_variants):
#     start_date = pd.to_datetime(start_date).date()
#     end_date = pd.to_datetime(end_date).date()
#
#     filtered_df = df.copy()
#
#     if 'ALL' not in selected_variants and selected_variants is not None and len(selected_variants) > 0:
#         filtered_df = filtered_df[filtered_df['variant'].isin(selected_variants)]
#
#     filtered_df = filtered_df[
#         (filtered_df['week_ending'].dt.date >= start_date) &
#         (filtered_df['week_ending'].dt.date <= end_date)
#     ]
#
#     filtered_df['share'] = filtered_df['share'] * 100
#     return filtered_df.to_dict('records')
#
# @app.callback(
#     Output('variant-distribution', 'figure'),
#     [Input('filtered-data', 'data'),
#      Input('graph-type-selector', 'value')])
# def update_graph(filtered_data, graph_type):
#     filtered_df = pd.DataFrame(filtered_data)
#
#     if filtered_df.empty or 'variant' not in filtered_df.columns:
#         return px.scatter(title="No data available for the selected criteria.")
#
#     if graph_type == 'box':
#         fig = px.box(filtered_df, x='variant', y='share',
#                      title="Distribution of SARS-CoV-2 Variant Proportions",
#                      labels={'share': 'Variant Proportion (%)', 'variant': 'Variant'},
#                      color='variant', notched=False)
#         fig.update_traces(hovertemplate='<b>%{x}</b><br>Proportion: %{y:.2f}%<extra></extra>')
#     elif graph_type == 'bar':
#         filtered_df = filtered_df.groupby('variant', as_index=False).agg({'share': 'mean'})
#         fig = px.bar(filtered_df, x='variant', y='share',
#                      title="Proportions of SARS-CoV-2 Variants",
#                      labels={'share': 'Variant Proportion (%)', 'variant': 'Variant'},
#                      color='variant')
#         fig.update_layout(xaxis={'categoryorder': 'total descending'})
#
#     fig.update_layout(transition_duration=500)
#     return fig
#
# # Run the app
# if __name__ == '__main__':
#     app.run_server(debug=False)

