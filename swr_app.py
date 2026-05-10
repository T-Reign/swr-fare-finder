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

# 2. DEFINE DEFAULTS
origin = None
destination = None
ticket_filter = []

if not all_stations:
    st.sidebar.error("No station data found in fares.zip!")
else:
    # 3. Initialize session state if not already set
    if 'origin_val' not in st.session_state:
        st.session_state.origin_val = "London Waterloo" if "London Waterloo" in all_stations else all_stations[0]
    if 'dest_val' not in st.session_state:
        st.session_state.dest_val = all_stations[1] if len(all_stations) > 1 else all_stations[0]

    # 4. Safe Index Lookup (This is what makes the flip visible in the UI)
    o_idx = all_stations.index(st.session_state.origin_val) if st.session_state.origin_val in all_stations else 0
    d_idx = all_stations.index(st.session_state.dest_val) if st.session_state.dest_val in all_stations else (1 if len(all_stations) > 1 else 0)

  # 5. Station Selectboxes - Linked directly to Session State
    # We add an 'on_change' or simply update the state manually
    origin = st.sidebar.selectbox(
        "Origin Station", 
        all_stations, 
        index=o_idx, 
        key="origin_select"
    )
    # Update memory immediately if the user clicks the box manually
    st.session_state.origin_val = origin

    destination = st.sidebar.selectbox(
        "Destination Station", 
        all_stations, 
        index=d_idx, 
        key="dest_select"
    )
    # Update memory immediately if the user clicks the box manually
    st.session_state.dest_val = destination

    # 6. The Reverse Button
    if st.sidebar.button("⇅ Reverse Journey"):
        # We swap the ACTUAL variables currently in the boxes
        old_origin = st.session_state.origin_val
        old_dest = st.session_state.dest_val
        
        st.session_state.origin_val = old_dest
        st.session_state.dest_val = old_origin
        
        # This is the "Magic" line: it clears the internal widget memory
        # so they are forced to look at o_idx and d_idx again
        if "origin_select" in st.session_state: del st.session_state["origin_select"]
        if "dest_select" in st.session_state: del st.session_state["dest_select"]
        
        st.rerun()
    
    # 7. Ticket Selection & Formatting
    ticket_data = df[['TICKET_TYPE_DESCRIPTION', 'TICKET_CODE']].drop_duplicates().dropna()
    ticket_options = []
    for _, row in ticket_data.iterrows():
        desc, code = str(row['TICKET_TYPE_DESCRIPTION']).strip(), str(row['TICKET_CODE']).strip()
        if not ("ADVANCE" in desc.upper() or code.startswith(('1', '2'))):
            ticket_options.append(f"{desc} ({code})")

    ticket_options = sorted(list(set(ticket_options)))
    default_selection = ticket_options[:2] if len(ticket_options) >= 2 else ticket_options

    selected_labels = st.sidebar.multiselect("Ticket Types", options=ticket_options, default=default_selection, key="ticket_multiselect")
    
    lock_baseline = st.sidebar.toggle("🔒 Lock Base Fare")
    
    # 8. Final Ticket Filter
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
        st.subheader(f"Potential Split Opportunities:")
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
