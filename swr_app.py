import streamlit as st
import pandas as pd

# --- 1. CONFIG & LOADING ---
st.set_page_config(page_title="SWR Split-Ticket Finder", layout="wide")

@st.cache_data
def load_data():
    import zipfile
    
    # 1. Open the zip file
    with zipfile.ZipFile('fares.zip', 'r') as z:
        # 2. Find the name of the CSV file inside (ignores hidden Mac folders)
        csv_files = [f for f in z.namelist() if f.endswith('.csv') and not f.startswith('__MACOSX')]
        
        if not csv_files:
            st.error("No CSV file found inside fares.zip!")
            return pd.DataFrame()
            
        # 3. Open that specific file
        with z.open(csv_files[0]) as f:
            df = pd.read_csv(f)
    
    # Standardize Column Names
    df.columns = df.columns.str.strip()
    
    # Convert FARE to numeric (pence to pounds)
    df['FARE'] = pd.to_numeric(df['FARE'], errors='coerce') / 100
    
    # Ensure TICKET_CODE exists
    if 'TICKET_CODE' not in df.columns:
        df['TICKET_CODE'] = 'N/A'
    else:
        df['TICKET_CODE'] = df['TICKET_CODE'].fillna('N/A')
        
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

# 1. Get unique values safely
origins = df['ORIGIN_CLEAN'].dropna().unique() if 'ORIGIN_CLEAN' in df.columns else []
destinations = df['DEST_CLEAN'].dropna().unique() if 'DEST_CLEAN' in df.columns else []
all_stations = sorted([str(s) for s in (set(origins) | set(destinations)) if s])

# 2. Initialize flip counter and values
if 'flip_count' not in st.session_state:
    st.session_state.flip_count = 0
if 'origin_val' not in st.session_state:
    st.session_state.origin_val = "London Waterloo" if "London Waterloo" in all_stations else all_stations[0]
if 'dest_val' not in st.session_state:
    st.session_state.dest_val = all_stations[1] if len(all_stations) > 1 else all_stations[0]

# 3. Define the Gatekeeper
if not all_stations:
    st.sidebar.error("No station data found!")
    origin, destination, ticket_filter, lock_baseline = None, None, [], False
else:
    # 4. Safe Index Lookup
    o_idx = all_stations.index(st.session_state.origin_val) if st.session_state.origin_val in all_stations else 0
    d_idx = all_stations.index(st.session_state.dest_val) if st.session_state.dest_val in all_stations else (1 if len(all_stations) > 1 else 0)

    # 5. STATION SELECTBOXES
    # The key changes every time we flip (origin_box_0, origin_box_1, etc.)
    # This forces Streamlit to refresh the widget completely.
    origin = st.sidebar.selectbox(
        "Origin Station", 
        all_stations, 
        index=o_idx, 
        key=f"origin_box_{st.session_state.flip_count}"
    )
    destination = st.sidebar.selectbox(
        "Destination Station", 
        all_stations, 
        index=d_idx, 
        key=f"dest_box_{st.session_state.flip_count}"
    )

    # 6. THE REVERSE BUTTON
    if st.sidebar.button("⇅ Reverse Journey"):
        # Swap the memory
        old_o = origin
        old_d = destination
        st.session_state.origin_val = old_d
        st.session_state.dest_val = old_o
        
        # Increment the counter to "kill" the old widgets and make new ones
        st.session_state.flip_count += 1
        st.rerun()

    st.sidebar.divider()
    
    # 7. Ticket Selection Logic
    ticket_data = df[['TICKET_TYPE_DESCRIPTION', 'TICKET_CODE']].drop_duplicates().dropna()
    ticket_options = sorted([f"{str(row['TICKET_TYPE_DESCRIPTION']).strip()} ({str(row['TICKET_CODE']).strip()})" 
                             for _, row in ticket_data.iterrows() 
                             if not ("ADVANCE" in str(row['TICKET_TYPE_DESCRIPTION']).upper() or str(row['TICKET_CODE']).startswith(('1', '2')))])

    default_vals = ticket_options[:2] if len(ticket_options) >= 2 else ticket_options
    selected_labels = st.sidebar.multiselect("Ticket Types", options=ticket_options, default=default_vals, key="ticket_type_search")
    lock_baseline = st.sidebar.toggle(
        "🔒 Lock Base Fare", 
        key="lock_base_toggle",
        help="When ON, the app compares split prices against the first ticket type in your list. When OFF, it compares against the cheapest available direct fare."
    )
    ticket_filter = [label.split(" (")[0] for label in selected_labels]

# --- 3. THE CALCULATION ENGINE ---
if origin and destination and ticket_filter:
    # 1. Determine the Baseline (Direct) Fare
    if lock_baseline:
        # If locked, we only look at the VERY FIRST ticket type in your multiselect list
        baseline_ticket = ticket_filter[0]
        direct_df = df[(df['TICKET_TYPE_DESCRIPTION'] == baseline_ticket)]
    else:
        # Otherwise, we look at all selected types
        direct_df = df[df['TICKET_TYPE_DESCRIPTION'].isin(ticket_filter)]

    # 2. FIND THE DIRECT ROW FOR THE CURRENT DIRECTION
    # We use 'origin' and 'destination' directly from the selectboxes
    direct_fare_row = direct_df[(direct_df['ORIGIN_CLEAN'] == origin) & 
                                (direct_df['DEST_CLEAN'] == destination)]
    
    if direct_fare_row.empty:
        st.warning(f"No direct fare found for {origin} to {destination}.")
    else:
        # Get the cheapest version of the direct ticket
        best_direct = direct_fare_row.loc[direct_fare_row['FARE'].idxmin()]
        direct_fare = best_direct['FARE']
        
        # 3. UPDATE THE HEADER AND METRIC
        # This ensures the text physically changes from "London to Brock" to "Brock to London"
        st.subheader(f"Direct Journey: {origin} to {destination}")
        
        lock_status = " (LOCKED)" if lock_baseline else ""
        st.metric(f"Direct Base Fare{lock_status}", f"£{direct_fare:.2f}", 
                  help=f"Reference: {best_direct['TICKET_TYPE_DESCRIPTION']} ({best_direct['TICKET_CODE']})")
        
        st.divider()
        # This label also needs to be dynamic!
        st.subheader(f"Potential Split Opportunities: {origin} to {destination}")

        filtered_df = df[df['TICKET_TYPE_DESCRIPTION'].isin(ticket_filter)]
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
                    # RE-APPLYING YOUR PREFERRED FORMATTING HERE:
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
            st.info("No split tickets found for these ticket types. :)")
            
# --- 4. DATA TABLE VIEW ---
with st.expander("View Raw Fare Data"):
    # Showing the TICKET_CODE column here too for consistency
    st.dataframe(df[(df['ORIGIN_CLEAN'] == origin) | (df['DEST_CLEAN'] == destination)])
