import streamlit as st
import pandas as pd

# --- 1. CONFIG & LOADING ---
st.set_page_config(page_title="SWR Split-Ticket Finder", layout="wide")

@st.cache_data
def load_data():
    # Pandas will automatically unzip the file 'fares.zip' 
    # and find the CSV inside it!
    df = pd.read_csv('fares.zip')
    
    # Keep your conversion logic here
    df['FARE'] = pd.to_numeric(df['FARE'], errors='coerce') / 100
    return df

df = load_data()

# --- THE UI DISPLAY ---
col1, col2 = st.columns([1, 5]) 

with col1:
    # Double check your file name here!
    st.image("SWR_Logo.png", width=100) 
with col2:
    st.markdown("# Split-Ticket Fare Finder")
    st.caption("Commercial Development Prototype for the Data Team")

st.divider()

# --- 2. SIDEBAR SEARCH ---
st.sidebar.header("Search Parameters")
all_stations = sorted(df['ORIGIN_CLEAN'].unique())

origin = st.sidebar.selectbox("Origin Station", all_stations, 
                             index=all_stations.index("London Waterloo") if "London Waterloo" in all_stations else 0)
destination = st.sidebar.selectbox("Destination Station", all_stations)

# Get the list of all unique ticket types found in YOUR data
available_tickets = sorted(df['TICKET_TYPE_DESCRIPTION'].unique())

# Set the default to the first two tickets in the list, so it never fails
default_selection = available_tickets[:2] if len(available_tickets) >= 2 else available_tickets

ticket_filter = st.sidebar.multiselect(
    "Ticket Types", 
    options=available_tickets,
    default=default_selection
)

# --- 3. THE CALCULATION ENGINE ---
if origin and destination:
    filtered_df = df[df['TICKET_TYPE_DESCRIPTION'].isin(ticket_filter)]
    direct_fare_row = filtered_df[(filtered_df['ORIGIN_CLEAN'] == origin) & 
                                  (filtered_df['DEST_CLEAN'] == destination)]
    
    if direct_fare_row.empty:
        st.warning(f"No direct fare found for selected ticket types. Try adding more types in the sidebar.")
    else:
        best_direct = direct_fare_row.loc[direct_fare_row['FARE'].idxmin()]
        direct_fare = best_direct['FARE']
        
        st.subheader(f"Direct Journey: {origin} to {destination}")
        st.metric("Cheapest Direct Fare", f"£{direct_fare:.2f}", help=f"Using: {best_direct['TICKET_TYPE_DESCRIPTION']}")
        
        st.divider()
        st.subheader("Potential Split Opportunities")

        possible_splits = filtered_df[filtered_df['ORIGIN_CLEAN'] == origin]['DEST_CLEAN'].unique()
        results = []

        for split_station in possible_splits:
            if split_station == destination or split_station == origin:
                continue
            
            l1_data = filtered_df[(filtered_df['ORIGIN_CLEAN'] == origin) & (filtered_df['DEST_CLEAN'] == split_station)]
            l2_data = filtered_df[(filtered_df['ORIGIN_CLEAN'] == split_station) & (filtered_df['DEST_CLEAN'] == destination)]

            if not l1_data.empty and not l2_data.empty:
                best_l1 = l1_data.loc[l1_data['FARE'].idxmin()]
                best_l2 = l2_data.loc[l2_data['FARE'].idxmin()]
                
                total_split = best_l1['FARE'] + best_l2['FARE']
                saving = direct_fare - total_split

                if saving > 0.01: # Show any saving at all
                    results.append({
                        "Split At": split_station,
                        "Leg 1": f"£{best_l1['FARE']:.2f} ({best_l1['TICKET_TYPE_DESCRIPTION']})",
                        "Leg 2": f"£{best_l2['FARE']:.2f} ({best_l2['TICKET_TYPE_DESCRIPTION']})",
                        "Total Price": f"£{total_split:.2f}",
                        "Saving": f"£{saving:.2f}",
                        "RawSaving": saving
                    })

        if results:
            results_df = pd.DataFrame(results).sort_values("RawSaving", ascending=False)
            st.dataframe(results_df.drop(columns=["RawSaving"]), use_container_width=True, hide_index=True)
            st.success(f"Found {len(results)} ways to save money!")
        else:
            st.info("No split savings found for these specific ticket types.")

# --- 4. DATA TABLE VIEW ---
with st.expander("View Raw Fare Data"):
    st.dataframe(df[(df['ORIGIN_CLEAN'] == origin) | (df['DEST_CLEAN'] == destination)])
