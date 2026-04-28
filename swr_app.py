import streamlit as st
import pandas as pd

# --- 1. CONFIG & LOADING ---
st.set_page_config(page_title="SWR Split-Ticket Finder", layout="wide")

@st.cache_data
def load_data():
    # Pandas will automatically unzip 'fares.zip'
    df = pd.read_csv('fares.zip')
    
    # Standardize Column Names just in case they have spaces
    df.columns = df.columns.str.strip()
    
    # Convert FARE to numeric (pence to pounds)
    df['FARE'] = pd.to_numeric(df['FARE'], errors='coerce') / 100
    
    # Ensure TICKET_CODE isn't empty (fills with 'N/A' if missing)
    if 'TICKET_CODE' in df.columns:
        df['TICKET_CODE'] = df['TICKET_CODE'].fillna('N/A')
    else:
        df['TICKET_CODE'] = 'N/A'
        
    return df

df = load_data()

# --- THE UI DISPLAY ---
col1, col2 = st.columns([1, 5]) 

with col1:
    st.image("SWR_Logo.png", width=100) 
with col2:
    st.markdown("# Split-Ticket Fare Finder")
    st.caption("Commercial Development Prototype for the Data Team")

st.divider()

# --- 2. SIDEBAR SEARCH ---
st.sidebar.header("Search Bar (SWR Only)")
all_stations = sorted(df['ORIGIN_CLEAN'].unique())

# Set default origin to London Waterloo
default_origin = "London Waterloo" if "London Waterloo" in all_stations else all_stations[0]

origin = st.sidebar.selectbox("Origin Station", all_stations, index=all_stations.index(default_origin))
destination = st.sidebar.selectbox("Destination Station", all_stations)

available_tickets = sorted(df['TICKET_TYPE_DESCRIPTION'].unique())
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
        st.warning(f"No direct fare found for selected ticket types.")
    else:
        best_direct = direct_fare_row.loc[direct_fare_row['FARE'].idxmin()]
        direct_fare = best_direct['FARE']
        
        # Display Direct Journey with the Code
        st.subheader(f"Direct Journey: {origin} to {destination}")
        st.metric("Cheapest Direct Fare", f"£{direct_fare:.2f}", 
                  help=f"Using: {best_direct['TICKET_TYPE_DESCRIPTION']} ({best_direct['TICKET_CODE']})")
        
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

                if saving > 0.01:
                    # FORMATTING THE LABELS AS REQUESTED: £5.50 (Description/Code)
                    leg1_label = f"£{best_l1['FARE']:.2f} ({best_l1['TICKET_TYPE_DESCRIPTION']}/{best_l1['TICKET_CODE']})"
                    leg2_label = f"£{best_l2['FARE']:.2f} ({best_l2['TICKET_TYPE_DESCRIPTION']}/{best_l2['TICKET_CODE']})"
                    
                    results.append({
                        "Split At": split_station,
                        "Leg 1": leg1_label,
                        "Leg 2": leg2_label,
                        "Total Price": f"£{total_split:.2f}",
                        "Saving": f"£{saving:.2f}",
                        "RawSaving": saving
                    })

        if results:
            results_df = pd.DataFrame(results).sort_values("RawSaving", ascending=False)
            st.dataframe(results_df.drop(columns=["RawSaving"]), use_container_width=True, hide_index=True)
            st.success(f"Found {len(results)} split ticket opportunities :(")
        else:
            st.info("No split tickets found for these specific ticket types :)")

# --- 4. DATA TABLE VIEW ---
with st.expander("View Raw Fare Data"):
    # Showing the TICKET_CODE column here too for consistency
    st.dataframe(df[(df['ORIGIN_CLEAN'] == origin) | (df['DEST_CLEAN'] == destination)])