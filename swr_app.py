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
                             if not str(row['TICKET_CODE']).startswith(('1', '2'))]) 

    default_vals = ticket_options[:2] if len(ticket_options) >= 2 else ticket_options
    selected_labels = st.sidebar.multiselect("Ticket Types", options=ticket_options, default=default_vals, key="ticket_type_search")
    lock_baseline = st.sidebar.toggle("🔒 Lock Base Fare", key="lock_base_toggle")
    # This grabs what is INSIDE the brackets: the actual ticket code!
ticket_filter = [label.split(" (")[1].replace(")", "") for label in selected_labels]

# --- 3. THE CALCULATION ENGINE (WITH ROUTING SEGMENTS) ---
if origin and destination and ticket_filter:

    # 🌟 MANAGER STEP: Define our core Line-of-Route sequences (The Train Tracks)
    # You can add more to this list gradually!
    SEQUENCES = {
        "South Western Main Line Via Woking": [
            "Weymouth", "Upwey", "Dorchester South", "Moreton (Dorset)", "Wool", "Wareham", "Holton Heath", "Hamworthy", "Poole", "Parkstone", "Branksome", "Bournemouth", "Pokesdown", "Christchurch", "Hinton Admiral", "New Milton", "Sway",
            "Brockenhurst", "Beaulieu Road", "Ashurst New Forest", "Totton", "Redbridge (Hants)", "Millbrook (Hants)", "Southampton Central", "St Denys", "Swaythling", "Southampton Airport Parkway", "Eastleigh", "Shawford", "Winchester", 
            "Micheldever", "Basingstoke", "Hook", "Winchfield", "Fleet", "Farnborough (Main)", "Brookwood", "Woking", "West Byfleet", "Byfleet & New Haw", "Weybridge", "Walton-On-Thames", "Hersham", "Esher", "Surbiton", "Berrylands", "New Malden",
            "Raynes Park", "Wimbledon", "Earlsfield", "Clapham Junction", "Queenstown Road (Battersea)", "London Waterloo"
        ],
        "West of England Line Via Woking": [
            "Exeter St Davids", "Exeter Central", "Pinhoe", "Cranbrook", "Whimple", "Feniton", "Honiton", "Axminster", "Crewkerne", "Yeovil Junction", "Sherbourne", "Templecombe", "Gillingham (Dorset)", "Tisbury", "Salisbury", "Grateley", "Andover",
            "Whitchurch (Hants)", "Overton", "Basingstoke", "Hook", "Winchfield", "Fleet", "Farnborough (Main)", "Brookwood", "Woking", "West Byfleet", "Byfleet & New Haw", "Weybridge", "Walton-On-Thames", "Hersham", "Esher", "Surbiton", "Berrylands", "New Malden",
            "Raynes Park", "Wimbledon", "Earlsfield", "Clapham Junction", "Queenstown Road (Battersea)", "London Waterloo"
        ],
        "Reading Line Via Twickenham": [
            "Reading", "Earley", "Winnersh Triangle", "Winnersh", "Wokingham", "Bracknell", "Martins Heron", "Ascot", "Sunningdale", "Longcross", "Virginia Water", "Egham", "Staines", "Ashford (Surrey)", "Feltham", "Whitton", "Twickenham", "St Margarets (London)",
            "Richmond (London)", "North Sheen", "Mortlake", "Barnes", "Putney", "Wandsworth Town", "Clapham Junction", "Queenstown Road (Battersea)", "London Waterloo"
        ],
         "Reading Line Via Brentford": [
            "Reading", "Earley", "Winnersh Triangle", "Winnersh", "Wokingham", "Bracknell", "Martins Heron", "Ascot", "Sunningdale", "Longcross", "Virginia Water", "Egham", "Staines", "Ashford (Surrey)", "Feltham", "Hounslow", "Isleworth", "Syon Lane", "Brentford",
             "Kew Bridge", "Chiswick", "Barnes Bridge", "Barnes", "Putney", "Wandsworth Town", "Clapham Junction", "Queenstown Road (Battersea)", "London Waterloo"
        ],
        "Winsdor Line Via Brentford": [
            "Windsor & Eton Riverside", "Datchet", "Sunneymeads", "Wraysbury", "Staines", "Ashford (Surrey)", "Feltham", "Hounslow", "Isleworth", "Syon Lane", "Brentford",
             "Kew Bridge", "Chiswick", "Barnes Bridge", "Barnes", "Putney", "Wandsworth Town", "Clapham Junction", "Queenstown Road (Battersea)", "London Waterloo"
        ],
        "Windsor Line Via Twickenham": [
            "Windsor & Eton Riverside", "Datchet", "Sunneymeads", "Wraysbury", "Staines", "Ashford (Surrey)", "Feltham", "Whitton", "Twickenham", "St Margarets (London)",
            "Richmond (London)", "North Sheen", "Mortlake", "Barnes", "Putney", "Wandsworth Town", "Clapham Junction", "Queenstown Road (Battersea)", "London Waterloo"
        ],
         "Weybridge Line Via Twickenham": [
            "Weybridge", "Addlestone", "Chertsey", "Virginia Water", "Egham", "Staines", "Ashford (Surrey)", "Feltham", "Whitton", "Twickenham", "St Margarets (London)",
            "Richmond (London)", "North Sheen", "Mortlake", "Barnes", "Putney", "Wandsworth Town", "Clapham Junction", "Queenstown Road (Battersea)", "London Waterloo"
        ],
         "Weybridge Line Via Brentford": [
            "Weybridge", "Addlestone", "Chertsey", "Virginia Water", "Egham", "Staines", "Ashford (Surrey)", "Feltham", "Hounslow", "Isleworth", "Syon Lane", "Brentford",
            "Kew Bridge", "Chiswick", "Barnes Bridge", "Barnes", "Putney", "Wandsworth Town", "Clapham Junction", "Queenstown Road (Battersea)", "London Waterloo"
        ],
        "Shepperton Line Via Twickenham": [
            "Shepperton", "Upper Halliford", "Sunbury", "Kempton Park", "Hampton (London)", "Fulwell", "Strawberry Hill", "Twickenham", "St Margarets (London)",
            "Richmond (London)", "North Sheen", "Mortlake", "Barnes", "Putney", "Wandsworth Town", "Clapham Junction", "Queenstown Road (Battersea)", "London Waterloo"
        ],
        "Shepperton Line Via Kingston": [
            "London Waterloo", "Queenstown Road (Battersea)", "Clapham Junction", "Earlsfield", "Wimbledon", "Raynes Park", "New Malden", "Norbiton", "Kingston", "Hampton Wick", "Teddington", "Fulwell", "Hampton (London)", "Kempton Park", "Sunbury", "Upper Halliford",
            "Shepperton"
        ],
        "Kingston Loop Via Twickenham": [
            "London Waterloo", "Queenstown Road (Battersea)", "Clapham Junction", "Earlsfield", "Wimbledon", "Raynes Park", "New Malden", "Norbiton", "Kingston", "Hampton Wick", "Teddington", "Strawberry Hill", "Twickenham", "St Margarets (London)",
            "Richmond (London)", "North Sheen", "Mortlake", "Barnes", "Putney", "Wandsworth Town", "Clapham Junction", "Queenstown Road (Battersea)", "London Waterloo"
        ],
        "Bagshot Line Via Twickenham": [
            "Alton", "Bentley (Hants)", "Farnham", "Aldershot", "Ash Vale", "Frimley", "Camberley", "Bagshot", "Ascot", "Sunningdale", "Longcross", "Virginia Water", "Egham", "Staines", "Ashford (Surrey)", "Feltham", "Whitton", "Twickenham", "St Margarets (London)",
            "Richmond (London)", "North Sheen", "Mortlake", "Barnes", "Putney", "Wandsworth Town", "Clapham Junction", "Queenstown Road (Battersea)", "London Waterloo"
        ],
         "Bagshot Line Via Brentford": [
            "Alton", "Bentley (Hants)", "Farnham", "Aldershot", "Ash Vale", "Frimley", "Camberley", "Bagshot", "Ascot", "Sunningdale", "Longcross", "Virginia Water", "Egham", "Staines", "Ashford (Surrey)", "Feltham", "Hounslow", "Isleworth", "Syon Lane", "Brentford",
             "Kew Bridge", "Chiswick", "Barnes Bridge", "Barnes", "Putney", "Wandsworth Town", "Clapham Junction", "Queenstown Road (Battersea)", "London Waterloo"
        ],
        "Portsmouth Direct Line": [
            "LONDON WATERLOO", "CLAPHAM JUNCTION", "SURBITON", "WOKING", 
            "GUILDFORD", "HASLEMERE", "PETERSFIELD", "HAVANT", "PORTSMOUTH HARBOUR"
        ],
        "Cross Country Coastway (Not London)": [
            "READING", "BASINGSTOKE", "WINCHESTER", "SOUTHAMPTON CENTRAL", 
            "FAREHAM", "HAVANT", "PORTSMOUTH HARBOUR"
        ]
    }

    # 1. Determine the Baseline (Direct) Fare
    if lock_baseline:
        baseline_ticket = ticket_filter[0]
        direct_df = df[(df['TICKET_CODE'] == baseline_ticket)]
    else:
        direct_df = df[df['TICKET_CODE'].isin(ticket_filter)]

    # 2. FIND THE DIRECT ROW FOR THE CURRENT DIRECTION
    direct_fare_row = direct_df[(direct_df['ORIGIN_CLEAN'] == origin) & 
                                (direct_df['DEST_CLEAN'] == destination)]
    
    if direct_fare_row.empty:
        st.warning(f"No direct fare found from {origin} to {destination}.")
    else:
        best_direct = direct_fare_row.loc[direct_fare_row['FARE'].idxmin()]
        direct_fare = best_direct['FARE']
        target_ticket_code = best_direct['TICKET_CODE']
        
        # 🌟 GRAB THE ROUTE DESCRIPTION (e.g., "ANY PERMITTED", "NOT LONDON", "VIA WOKING")
        # If your data column has a slightly different name, change 'ROUTE_DESCRIPTION' to match it
        route_desc = str(best_direct.get('ROUTE_DESCRIPTION', 'ANY PERMITTED')).upper()
        
        # 3. UPDATE THE HEADER AND METRIC
        st.subheader(f"Direct Journey: {origin} to {destination}")
        
        lock_status = " (LOCKED)" if lock_baseline else ""
        st.metric(f"Direct Base Fare{lock_status}", f"£{direct_fare:.2f}", 
                  help=f"Reference: {best_direct['TICKET_TYPE_DESCRIPTION']} ({target_ticket_code}) | Route: {route_desc}")
        
        st.divider()
        st.subheader(f"Potential Split Opportunities: {origin} to {destination}")

        # 🌟🌟🌟 THE SMART GEOGRAPHY FILTER 🌟🌟🌟
        # Figure out which of our Sequences are physically valid for this ticket's route rules
        valid_split_stations = set()
        
        for seq_name, station_list in SEQUENCES.items():
            seq_upper = [s.upper() for s in station_list]
            
            # Check if both our Origin and Destination exist on this specific track line
            if origin.upper() in seq_upper and destination.upper() in seq_upper:
                
                # ROUTE RULE A: If the ticket says "NOT LONDON", skip any sequence containing London!
                if "NOT LONDON" in route_desc and "LONDON WATERLOO" in seq_upper:
                    continue
                
                # ROUTE RULE B: If it specifies a "VIA", make sure that station is actually in the sequence
                if "VIA" in route_desc:
                    # e.g., if route is "VIA WOKING", check if WOKING is in this track line
                    via_station = route_desc.replace("VIA ", "").strip()
                    if via_station not in seq_upper:
                        continue
                
                # If it passed the rules, find the stations sitting physically between our start and end
                idx1, idx2 = seq_upper.index(origin.upper()), seq_upper.index(destination.upper())
                start_idx, end_idx = min(idx1, idx2), max(idx1, idx2)
                
                # Add these middle stations to our allowed split pool
                valid_split_stations.update(station_list[start_idx+1:end_idx])

        # Now search for splits ONLY using our geographically approved station pool
        filtered_df = df[df['TICKET_CODE'] == target_ticket_code]
        results = []

        for split_station in valid_split_stations:
            l1_data = filtered_df[(filtered_df['ORIGIN_CLEAN'].str.upper() == origin.upper()) & (filtered_df['DEST_CLEAN'].str.upper() == split_station.upper())]
            l2_data = filtered_df[(filtered_df['ORIGIN_CLEAN'].str.upper() == split_station.upper()) & (filtered_df['DEST_CLEAN'].str.upper() == destination.upper())]

            if not l1_data.empty and not l2_data.empty:
                best_l1 = l1_data.loc[l1_data['FARE'].idxmin()]
                best_l2 = l2_data.loc[l2_data['FARE'].idxmin()]
                
                total_split = best_l1['FARE'] + best_l2['FARE']
                saving = direct_fare - total_split

                if saving > 0.01:
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
            st.success(f"Found {len(results)} split opportunities :(")
        else:
            st.info("No valid line-of-route splits found for this ticket code tier. :)")
            
# --- 4. DATA TABLE VIEW ---
with st.expander("View Raw Fare Data"):
    # Showing the TICKET_CODE column here too for consistency
    st.dataframe(df[(df['ORIGIN_CLEAN'] == origin) | (df['DEST_CLEAN'] == destination)])
