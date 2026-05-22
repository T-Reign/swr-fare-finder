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

# 🌟 FIX: Use a unique state variable name to avoid locking conflicts
if 'selected_tickets_memory' not in st.session_state:
    st.session_state.selected_tickets_memory = None

# 3. Define the Gatekeeper
if not all_stations:
    st.sidebar.error("No station data found!")
    origin, destination, ticket_filter, lock_baseline = None, None, [], False
else:
    # 4. Safe Index Lookup
    o_idx = all_stations.index(st.session_state.origin_val) if st.session_state.origin_val in all_stations else 0
    d_idx = all_stations.index(st.session_state.dest_val) if st.session_state.dest_val in all_stations else (1 if len(all_stations) > 1 else 0)

    # 5. STATION SELECTBOXES
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
        # 🌟 SAVE CURRENT SELECTIONS TO MEMORY BEFORE FLIPPING
        if "ticket_type_search" in st.session_state:
            st.session_state.selected_tickets_memory = st.session_state.ticket_type_search

        # Swap the station memory
        old_o = origin
        old_d = destination
        st.session_state.origin_val = old_d
        st.session_state.dest_val = old_o
        
        # Force the widget recreation
        st.session_state.flip_count += 1
        st.rerun()

    st.sidebar.divider()
    
   # 7. Ticket Selection Logic
    ticket_data = df[['TICKET_TYPE_DESCRIPTION', 'TICKET_CODE']].drop_duplicates().dropna()
    ticket_options = sorted([f"{str(row['TICKET_TYPE_DESCRIPTION']).strip()} ({str(row['TICKET_CODE']).strip()})" 
                             for _, row in ticket_data.iterrows() 
                             if not str(row['TICKET_CODE']).startswith(('1', '2'))]) 

    # 🌟 FIX: If memory is empty, set your standard fallback default values
    if st.session_state.selected_tickets_memory is None:
        st.session_state.selected_tickets_memory = ticket_options[:2] if len(ticket_options) >= 2 else ticket_options

    # Pass the memory directly into 'default' and use a clean key string
    selected_labels = st.sidebar.multiselect(
        "Ticket Types", 
        options=ticket_options, 
        default=st.session_state.selected_tickets_memory, 
        key="ticket_type_search"
    )
    
    lock_baseline = st.sidebar.toggle("🔒 Lock Base Fare", key="lock_base_toggle")
    
ticket_filter = [label.split(" (")[1].replace(")", "") for label in selected_labels]

# --- 3. THE CALCULATION ENGINE (WITH ROUTING SEGMENTS) ---
if origin and destination and ticket_filter:

    # SEQUENCES Matrix
    SEQUENCES = {
        "South Western Main Line Via Woking": [
            "Weymouth", "Upwey", "Dorchester South", "Moreton (Dorset)", "Wool", "Wareham", "Holton Heath", "Hamworthy", "Poole", "Parkstone", "Branksome", "Bournemouth", "Pokesdown", "Christchurch", "Hinton Admiral", "New Milton", "Sway",
            "Brockenhurst", "Beaulieu Road", "Ashurst New Forest", "Totton", "Redbridge (Hants)", "Millbrook (Hants)", "Southampton Central", "St Denys", "Swaythling", "Southampton Airport Parkway", "Eastleigh", "Shawford", "Winchester", 
            "Micheldever", "Basingstoke", "Hook", "Winchfield", "Fleet", "Farnborough (Main)", "Brookwood", "Woking", "West Byfleet", "Byfleet & New Haw", "Weybridge", "Walton-On-Thames", "Hersham", "Esher", "Surbiton", "Berrylands", "New Malden",
            "Raynes Park", "Wimbledon", "Earlsfield", "Clapham Junction", "Queenstown Road (Battersea)", "London Waterloo"
        ],
        "Lymington to Waterloo Via Woking": [
            "Lymington Pier", "Lymington Town", "Brockenhurst", "Beaulieu Road", "Ashurst New Forest", "Totton", "Redbridge (Hants)", "Millbrook (Hants)", "Southampton Central", "St Denys", "Swaythling", "Southampton Airport Parkway", "Eastleigh", "Shawford", "Winchester", 
            "Micheldever", "Basingstoke", "Hook", "Winchfield", "Fleet", "Farnborough (Main)", "Brookwood", "Woking", "West Byfleet", "Byfleet & New Haw", "Weybridge", "Walton-On-Thames", "Hersham", "Esher", "Surbiton", "Berrylands", "New Malden",
            "Raynes Park", "Wimbledon", "Earlsfield", "Clapham Junction", "Queenstown Road (Battersea)", "London Waterloo"
        ],
        "Southampton Line Via Woking": [
            "Swanwick", "Bursledon", "Hamble", "Netley", "Sholing", "Woolston", "Bitterne", "St Denys", "Southampton Central", "St Denys", "Swaythling", "Southampton Airport Parkway", "Eastleigh", "Shawford", "Winchester", 
            "Micheldever", "Basingstoke", "Hook", "Winchfield", "Fleet", "Farnborough (Main)", "Brookwood", "Woking", "West Byfleet", "Byfleet & New Haw", "Weybridge", "Walton-On-Thames", "Hersham", "Esher", "Surbiton", "Berrylands", "New Malden",
            "Raynes Park", "Wimbledon", "Earlsfield", "Clapham Junction", "Queenstown Road (Battersea)", "London Waterloo"
        ],
        "Romsey Rounders to Waterloo Via Winchester": [
            "Dean", "Mottisfont & Dunbridge", "Romsey", "Redbridge", "Millbrook", "Southampton Central", "St Denys", "Swaythling", "Southampton Airport Parkway", "Chandler's Ford", "Eastleigh", "Shawford", "Winchester", 
            "Micheldever", "Basingstoke", "Hook", "Winchfield", "Fleet", "Farnborough (Main)", "Brookwood", "Woking", "West Byfleet", "Byfleet & New Haw", "Weybridge", "Walton-On-Thames", "Hersham", "Esher", "Surbiton", "Berrylands", "New Malden",
            "Raynes Park", "Wimbledon", "Earlsfield", "Clapham Junction", "Queenstown Road (Battersea)", "London Waterloo"
        ],
        "West of England Line Via Woking": [
            "Exeter St Davids", "Exeter Central", "Pinhoe", "Cranbrook", "Whimple", "Feniton", "Honiton", "Axminster", "Crewkerne", "Yeovil Junction", "Sherbourne", "Templecombe", "Gillingham (Dorset)", "Tisbury", "Salisbury", "Grateley", "Andover",
            "Whitchurch (Hants)", "Overton", "Basingstoke", "Hook", "Winchfield", "Fleet", "Farnborough (Main)", "Brookwood", "Woking", "West Byfleet", "Byfleet & New Haw", "Weybridge", "Walton-On-Thames", "Hersham", "Esher", "Surbiton", "Berrylands", "New Malden",
            "Raynes Park", "Wimbledon", "Earlsfield", "Clapham Junction", "Queenstown Road (Battersea)", "London Waterloo"
        ],
        "Romsey Rounders to Waterloo via Andover": [
            "Chandler's Ford", "Romsey", "Mottisfont & Dunbridge", "Dean", "Salisbury", "Grateley", "Andover",
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
        "Chessington Line": [
            "London Waterloo", "Queenstown Road (Battersea)", "Clapham Junction", "Earlsfield", "Wimbledon", "Raynes Park", "Motspur Park", "Malden Manor", "Tolworth", "Chessington North", "Chessington South"
        ],
        "Guildford Line via Epsom": [
            "London Waterloo", "Queenstown Road (Battersea)", "Clapham Junction", "Earlsfield", "Wimbledon", "Raynes Park", "Motspur Park", "Worcester Park", "Stoneleigh", "Ewell West", "Epsom", "Ashtead", "Leatherhead", "Bookham", "Effingham Junction", "Horsley", 
            "Clandon", "London Road (Guildford)", "Guildford"
        ],
        "Guildford Line via Claygate": [
            "London Waterloo", "Queenstown Road (Battersea)", "Clapham Junction", "Earlsfield", "Wimbledon", "Raynes Park", "New Malden", "Berrylands", "Surbiton", "Hinchley Wood", "Claygate", "Oxshott", "Cobham & D'Abernon", "Effingham Junction", "Horsley", 
            "Clandon", "London Road (Guildford)", "Guildford"
        ],
        "Hampton Court Line": [
            "London Waterloo", "Queenstown Road (Battersea)", "Clapham Junction", "Earlsfield", "Wimbledon", "Raynes Park", "New Malden", "Berrylands", "Surbiton", "Thames Ditton", "Hampton Court"
        ],
        "Dorking Line": [
            "London Waterloo", "Queenstown Road (Battersea)", "Clapham Junction", "Earlsfield", "Wimbledon", "Raynes Park", "Motspur Park", "Worcester Park", "Stoneleigh", "Ewell West", "Epsom", "Ashtead", "Leatherhead", "Box Hill & Westhumble", "Dorking"
        ],
        "Kingston Loop Via Twickenham": [
            "London Waterloo", "Queenstown Road (Battersea)", "Clapham Junction", "Earlsfield", "Wimbledon", "Raynes Park", "New Malden", "Norbiton", "Kingston", "Hampton Wick", "Teddington", "Strawberry Hill", "Twickenham", "St Margarets (London)",
            "Richmond (London)", "North Sheen", "Mortlake", "Barnes", "Putney", "Wandsworth Town", "Clapham Junction", "Queenstown Road (Battersea)", "London Waterloo"
        ],
        "Hounslow Loop Via Twickenham": [
            "London Waterloo", "Queenstown Road (Battersea)", "Clapham Junction", "Wandsworth Town", "Putney", "Barnes", "Barnes Bridge", "Chiswick", "Kew Bridge", "Brentford", "Syon Lane", "Isleworth", "Hounslow", "Whitton", "Twickenham", "St Margarets (London)",
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
            "London Waterloo", "Queenstown Road (Battersea)", "Clapham Junction", "Earlsfield", "Wimbledon", "Raynes Park", "New Malden", "Berrylands", "Surbiton", "Esher", "Hersham", "Walton-On-Thames", "Weybridge", "Byfleet & New Haw", "West Byfleet", "Woking", 
            "Worplesdon", "Guildford", "Farncombe", "Godalming", "Milford (Surrey)", "Witley", "Haslemere", "Liphook", "Liss", "Petersfield", "Rowlands Castle", "Havant", "Bedhampton", "Hilsea", "Fratton", "Portsmouth & Southsea", "Portsmouth Harbour"
        ],
        "Portsmouth via Basingstoke Line": [
            "London Waterloo", "Queenstown Road (Battersea)", "Clapham Junction", "Earlsfield", "Wimbledon", "Raynes Park", "New Malden", "Berrylands", "Surbiton", "Esher", "Hersham", "Walton-On-Thames", "Weybridge", "Byfleet & New Haw", "West Byfleet", "Woking", 
            "Brookwood", "Farnborough (Main)", "Fleet", "Winchfield", "Hook", "Basingstoke", "Micheldever", "Winchester", "Shawford", "Eastleigh", "Hedge End", "Botley", "Fareham", "Portchester", "Cosham", "Hilsea", "Fratton", "Portsmouth & Southsea", 
            "Portsmouth Harbour"
        ],
        "Alton Line": [
            "London Waterloo", "Queenstown Road (Battersea)", "Clapham Junction", "Earlsfield", "Wimbledon", "Raynes Park", "New Malden", "Berrylands", "Surbiton", "Esher", "Hersham", "Walton-On-Thames", "Weybridge", "Byfleet & New Haw", "West Byfleet", "Woking", 
            "Brookwood", "Ash Vale", "Aldershot", "Farnham", "Bentley (Hants)", "Alton"
        ],
        "Reading Line to Alton via Ascot": [
            "Reading", "Earley", "Winnersh Triangle", "Winnersh", "Wokingham", "Bracknell", "Martins Heron", "Ascot", "Bagshot", "Camberley", "Frimley", "Ash Vale", "Aldershot", "Farnham", "Bentley (Hants)", "Alton"
        ],
        "Reading Line to Alton via Ash": [
            "Reading", "Earley", "Winnersh Triangle", "Winnersh", "Wokingham", "Crowthorne", "Sandhurst", "Blackwater", "Ash", "Aldershot", "Farnham", "Bentley (Hants)", "Alton"
        ],
        "West of England Line to Portsmouth Line via Woking": [
            "Exeter St Davids", "Exeter Central", "Pinhoe", "Cranbrook", "Whimple", "Feniton", "Honiton", "Axminster", "Crewkerne", "Yeovil Junction", "Sherbourne", "Templecombe", "Gillingham (Dorset)", "Tisbury", "Salisbury", "Grateley", "Andover",
            "Whitchurch (Hants)", "Overton", "Basingstoke", "Hook", "Winchfield", "Fleet", "Farnborough (Main)", "Brookwood", "Woking", "Worplesdon", "Guildford", "Farncombe", "Godalming", "Milford (Surrey)", "Witley", "Haslemere", "Liphook", "Liss", "Petersfield", 
            "Rowlands Castle", "Havant", "Bedhampton", "Hilsea", "Fratton", "Portsmouth & Southsea", "Portsmouth Harbour"
        ],
        "West of England Line to Alton Line via Woking": [
            "Exeter St Davids", "Exeter Central", "Pinhoe", "Cranbrook", "Whimple", "Feniton", "Honiton", "Axminster", "Crewkerne", "Yeovil Junction", "Sherbourne", "Templecombe", "Gillingham (Dorset)", "Tisbury", "Salisbury", "Grateley", "Andover",
            "Whitchurch (Hants)", "Overton", "Basingstoke", "Hook", "Winchfield", "Fleet", "Farnborough (Main)", "Brookwood", "Woking", "Brookwood", "Ash Vale", "Aldershot", "Farnham", "Bentley (Hants)", "Alton"
        ],
        "South Western Main Line & PDL": [
            "Weymouth", "Upwey", "Dorchester South", "Moreton (Dorset)", "Wool", "Wareham", "Holton Heath", "Hamworthy", "Poole", "Parkstone", "Branksome", "Bournemouth", "Pokesdown", "Christchurch", "Hinton Admiral", "New Milton", "Sway",
            "Brockenhurst", "Beaulieu Road", "Ashurst New Forest", "Totton", "Redbridge (Hants)", "Millbrook (Hants)", "Southampton Central", "St Denys", "Swaythling", "Southampton Airport Parkway", "Eastleigh", "Shawford", "Winchester", 
            "Micheldever", "Basingstoke", "Hook", "Winchfield", "Fleet", "Farnborough (Main)", "Brookwood", "Woking", "Worplesdon", "Guildford", "Farncombe", "Godalming", "Milford (Surrey)", "Witley", "Haslemere", "Liphook", "Liss", "Petersfield", 
            "Rowlands Castle", "Havant", "Bedhampton", "Hilsea", "Fratton", "Portsmouth & Southsea", "Portsmouth Harbour"
        ],
        "Alton & PDL Lines": [
            "Alton", "Bentley (Hants)", "Farnham", "Aldershot", "Ash Vale", "Brookwood", "Woking", "Worplesdon", "Guildford", "Farncombe", "Godalming", "Milford (Surrey)", "Witley", "Haslemere", "Liphook", "Liss", "Petersfield", 
            "Rowlands Castle", "Havant", "Bedhampton", "Hilsea", "Fratton", "Portsmouth & Southsea", "Portsmouth Harbour"
        ],
        "Ash & PDL Lines": [
            "Alton", "Bentley (Hants)", "Farnham", "Aldershot", "Ash", "Wanborough", "Guildford", "Farncombe", "Godalming", "Milford (Surrey)", "Witley", "Haslemere", "Liphook", "Liss", "Petersfield", 
            "Rowlands Castle", "Havant", "Bedhampton", "Hilsea", "Fratton", "Portsmouth & Southsea", "Portsmouth Harbour"
        ],
        "Ascot to PDL Lines via Aldershot": [
            "Ascot", "Bagshot", "Camberley", "Frimley", "Ash Vale", "Aldershot", "Ash", "Wanborough", "Guildford", "Farncombe", "Godalming", "Milford (Surrey)", "Witley", "Haslemere", "Liphook", "Liss", "Petersfield", 
            "Rowlands Castle", "Havant", "Bedhampton", "Hilsea", "Fratton", "Portsmouth & Southsea", "Portsmouth Harbour"
        ],
        "Ascot to PDL Lines via Brookwood": [
            "Ascot", "Bagshot", "Camberley", "Frimley", "Ash Vale", "Brookwood", "Woking", "Worplesdon", "Guildford", "Farncombe", "Godalming", "Milford (Surrey)", "Witley", "Haslemere", "Liphook", "Liss", "Petersfield", 
            "Rowlands Castle", "Havant", "Bedhampton", "Hilsea", "Fratton", "Portsmouth & Southsea", "Portsmouth Harbour"
        ],
        "Bracknell to PDL Lines via Addlestone": [
            "Bracknell", "Martins Heron", "Ascot", "Sunningdale", "Longcross", "Virginia Water", "Addlestone", "Chertsey", "Weybridge", "Byfleet & New Haw", "West Byfleet", "Woking", "Worplesdon", "Guildford", "Farncombe", "Godalming", "Milford (Surrey)",
            "Witley", "Haslemere", "Liphook", "Liss", "Petersfield", "Rowlands Castle", "Havant", "Bedhampton", "Hilsea", "Fratton", "Portsmouth & Southsea", "Portsmouth Harbour"
        ],
        "Reading to PDL Line via Blackwater": [
            "Reading", "Earley", "Winnersh Triangle", "Winnersh", "Wokingham", "Ash", "Wanborough", "Guildford", "Farncombe", "Godalming", "Milford (Surrey)", "Witley", "Haslemere", "Liphook", "Liss", "Petersfield", 
            "Rowlands Castle", "Havant", "Bedhampton", "Hilsea", "Fratton", "Portsmouth & Southsea", "Portsmouth Harbour"
        ],
        "Ascot to PDL Line via Blackwater": [
            "Ascot", "Martins Heron", "Bracknell", "Wokingham", "Ash", "Wanborough", "Guildford", "Farncombe", "Godalming", "Milford (Surrey)", "Witley", "Haslemere", "Liphook", "Liss", "Petersfield", 
            "Rowlands Castle", "Havant", "Bedhampton", "Hilsea", "Fratton", "Portsmouth & Southsea", "Portsmouth Harbour"
        ],
        "Reading to Epsom via Blackwater": [
            "Reading", "Earley", "Winnersh Triangle", "Winnersh", "Wokingham", "Ash", "Wanborough", "Guildford", "London Road (Guildford)", "Clandon", "Horsley", "Effingham Junction", "Bookham", "Leatherhead", "Ashtead", "Epsom"
        ],
        "Reading to Dorking via Blackwater": [
            "Reading", "Earley", "Winnersh Triangle", "Winnersh", "Wokingham", "Ash", "Wanborough", "Guildford", "London Road (Guildford)", "Clandon", "Horsley", "Effingham Junction", "Bookham", "Leatherhead", "Box Hill & Westhumble", "Dorking"
        ],
        "Ascot to Epsom via Blackwater": [
            "Ascot", "Martins Heron", "Bracknell", "Wokingham", "Ash", "Wanborough", "Guildford", "London Road (Guildford)", "Clandon", "Horsley", "Effingham Junction", "Bookham", "Leatherhead", "Ashtead", "Epsom"
        ],
        "Ascot to Dorking via Blackwater": [
            "Ascot", "Martins Heron", "Bracknell", "Wokingham", "Ash", "Wanborough", "Guildford", "London Road (Guildford)", "Clandon", "Horsley", "Effingham Junction", "Bookham", "Leatherhead", "Box Hill & Westhumble", "Dorking"
        ],
        "Ascot to Epsom via Aldershot": [
            "Ascot", "Bagshot", "Camberley", "Frimley", "Ash Vale", "Aldershot", "Ash", "Wanborough", "Guildford", "London Road (Guildford)", "Clandon", "Horsley", "Effingham Junction", "Bookham", "Leatherhead", "Ashtead", "Epsom"
        ],
        "Ascot to Dorking via Aldershot": [
            "Ascot", "Bagshot", "Camberley", "Frimley", "Ash Vale", "Aldershot", "Ash", "Wanborough", "Guildford", "London Road (Guildford)", "Clandon", "Horsley", "Effingham Junction", "Bookham", "Leatherhead", "Box Hill & Westhumble", "Dorking"
        ],
        "Reading to Surbiton via Clandon": [
            "Reading", "Earley", "Winnersh Triangle", "Winnersh", "Wokingham", "Ash", "Wanborough", "Guildford", "London Road (Guildford)", "Clandon", "Horsley", "Effingham Junction", "Cobham & Stoke D'Abernon", "Oxshott", "Claygate", "Hinchley Wood", "Surbiton"
        ],
        "Reading to Surbiton via Woking": [
            "Reading", "Earley", "Winnersh Triangle", "Winnersh", "Wokingham", "Ash", "Wanborough", "Guildford", "Worplesdon", "Woking", "West Byfleet", "Byfleet & New Haw", "Weybridge", "Walton-On-Thames", "Hersham", "Esher", "Surbiton"
        ],
        "Ascot to Hinchley Wood via Clandon": [
            "Ascot", "Bagshot", "Camberley", "Frimley", "Ash Vale", "Aldershot", "Ash", "Wanborough", "Guildford", "London Road (Guildford)", "Clandon", "Horsley", "Effingham Junction", "Cobham & Stoke D'Abernon", "Oxshott", "Claygate", "Hinchley Wood"
        ],
        "Ascot to Oxshott via Woking": [
            "Ascot", "Bagshot", "Camberley", "Frimley", "Ash Vale", "Brookwood", "Woking", "West Byfleet", "Byfleet & New Haw", "Weybridge", "Walton-On-Thames", "Hersham", "Esher", "Surbiton", "Hincley Wood", "Claygate", "Oxshott"
        ],
        "Alton to Hinchley Wood via Clandon": [
            "Alton", "Bentley (Hants)", "Farnham", "Aldershot", "Ash", "Wanborough", "Guildford", "London Road (Guildford)", "Clandon", "Horsley", "Effingham Junction", "Cobham & Stoke D'Abernon", "Oxshott", "Claygate", "Hinchley Wood"
        ],
        "Alton to Oxshott via Woking": [
            "Alton", "Bentley (Hants)", "Farnham", "Aldershot", "Ash Vale", "Brookwood", "Woking", "West Byfleet", "Byfleet & New Haw", "Weybridge", "Walton-On-Thames", "Hersham", "Esher", "Surbiton", "Hincley Wood", "Claygate", "Oxshott"
        ],
        "Alton to Epsom via Guildford": [
            "Alton", "Bentley (Hants)", "Farnham", "Aldershot", "Ash", "Wanborough", "Guildford", "London Road (Guildford)", "Clandon", "Horsley", "Effingham Junction", "Bookham", "Leatherhead", "Ashtead", "Epsom"
        ],
        "Alton to Dorking via Guildford": [
            "Alton", "Bentley (Hants)", "Farnham", "Aldershot", "Ash", "Wanborough", "Guildford", "London Road (Guildford)", "Clandon", "Horsley", "Effingham Junction", "Bookham", "Leatherhead", "Box Hill & Westhumble", "Dorking"
        ],
        "Alton to Chertsey via Brookwood": [
            "Alton", "Bentley (Hants)", "Farnham", "Aldershot", "Ash Vale", "Brookwood", "Woking", "West Byfleet", "Byfleet & New Haw", "Weybridge", "Addlestone", "Chertsey"
        ],
        "Alton to Addlestone via Ascot": [
            "Alton", "Bentley (Hants)", "Farnham", "Aldershot", "Ash Vale", "Frimley", "Camberley", "Bagshot", "Ascot", "Sunningdale", "Longcross", "Virginia Water", "Chertsey", "Addlestone"
        ],
        "Ash to Chertsey via Guildford": [
            "Ash", "Wanborough", "Guildford", "Worplesdon", "Woking", "West Byfleet", "Byfleet & New Haw", "Weybridge", "Addlestone", "Chertsey"
        ],
        "Wanborough to Addlestone via Bagshot": [
            "Wanborough", "Ash", "Aldershot", "Ash Vale", "Frimley", "Camberley", "Bagshot", "Ascot", "Sunningdale", "Longcross", "Virginia Water", "Chertsey", "Addlestone"
        ],
        "Worplesdon to Alton via Guildford": [
            "Alton", "Bentley (Hants)", "Farnham", "Aldershot", "Ash", "Wanborough", "Guildford", "Worplesdon"
        ],
        "Worplesdon to Alton via Brookwood": [
            "Alton", "Bentley (Hants)", "Farnham", "Aldershot", "Ash Vale", "Brookwood", "Woking", "Worplesdon"
        ],
        "Worplesdon to Ascot via Guildford": [
            "Ascot", "Bagshot", "Camberley", "Frimley", "Ash Vale", "Aldershot", "Ash", "Wanborough", "Guildford", "Worplesdon"
        ],
        "Worplesdon to Ascot via Brookwood": [
            "Ascot", "Bagshot", "Camberley", "Frimley", "Ash Vale", "Brookwood", "Woking", "Worplesdon"
        ],
        "Worplesdon to Epsom via Aldershot": [
            "Worplesdon", "Guildford", "London Road (Guildford)", "Clandon", "Horsley", "Effingham Junction", "Bookham", "Leatherhead", "Ashtead", "Epsom"
        ],
        "Worplesdon to Dorking via Aldershot": [
            "Worplesdon", "Guildford", "London Road (Guildford)", "Clandon", "Horsley", "Effingham Junction", "Bookham", "Leatherhead", "Box Hill & Westhumble", "Dorking"
        ],
        "Weymouth to Portsmouth Line via Fratton": [
            "Weymouth", "Upwey", "Dorchester South", "Moreton (Dorset)", "Wool", "Wareham", "Holton Heath", "Hamworthy", "Poole", "Parkstone", "Branksome", "Bournemouth", "Pokesdown", "Christchurch", "Hinton Admiral", "New Milton", "Lymington Pier", "Lymington Town", "Sway",
            "Brockenhurst", "Beaulieu Road", "Ashurst New Forest", "Totton", "Redbridge (Hants)", "Millbrook (Hants)", "Southampton Central", "St Denys", "Bitterne", "Woolston", "Sholing", "Netley", "Hamble", "Bursledon", "Swanwick", "Fareham", "Portchester", 
            "Cosham", "Hilsea", "Fratton", "Portsmouth & Southsea", "Portsmouth Harbour"
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
        
        # Grab route description and scrub whitespace
        route_desc = str(best_direct.get('ROUTE_DESCRIPTION', 'ANY PERMITTED')).strip().upper()
        
        # 3. UPDATE THE HEADER AND METRIC
        st.subheader(f"Direct Journey: {origin} to {destination}")
        
        lock_status = " (LOCKED)" if lock_baseline else ""
        st.metric(f"Direct Base Fare{lock_status}", f"£{direct_fare:.2f}", 
                  help=f"Reference: {best_direct['TICKET_TYPE_DESCRIPTION']} ({target_ticket_code}) | Route: {route_desc}")
        
        st.divider()
        st.subheader(f"Potential Split Opportunities: {origin} to {destination}")

        # THE SMART GEOGRAPHY FILTER
        # 🌟🌟🌟 UPDATED GEOGRAPHY FILTER FOR TRANSFER JOURNEYS 🌟🌟🌟
        valid_split_stations = set()
        direct_match_found = False

        # Leg 1: Look for direct single-sequence paths
        for seq_name, station_list in SEQUENCES.items():
            seq_upper = [s.strip().upper() for s in station_list]
            if origin.upper() in seq_upper and destination.upper() in seq_upper:
                idx1, idx2 = seq_upper.index(origin.upper()), seq_upper.index(destination.upper())
                start_idx, end_idx = min(idx1, idx2), max(idx1, idx2)
                valid_split_stations.update(station_list[start_idx+1:end_idx])
                direct_match_found = True

        # Leg 2: If it's a cross-country route, find a connecting interchange station
        if not direct_match_found:
            for seq1_name, seq1_list in SEQUENCES.items():
                seq1_upper = [s.strip().upper() for s in seq1_list]
                if origin.upper() in seq1_upper:
            
                    for seq2_name, seq2_list in SEQUENCES.items():
                        seq2_upper = [s.strip().upper() for s in seq2_list]
                        if destination.upper() in seq2_upper:
                    
                            # Find common stations where these two master tracks cross
                            common_interchanges = set(seq1_upper).intersection(set(seq2_upper))
                    
                            for interchange in common_interchanges:
                                # Extract stations from Origin to Interchange
                                idx_orig = seq1_upper.index(origin.upper())
                                idx_int1 = seq1_upper.index(interchange)
                                s1, e1 = min(idx_orig, idx_int1), max(idx_orig, idx_int1)
                                valid_split_stations.update(seq1_list[s1+1:e1])
                        
                                # Extract stations from Interchange to Destination
                                idx_int2 = seq2_upper.index(interchange)
                                idx_dest = seq2_upper.index(destination.upper())
                                s2, e2 = min(idx_int2, idx_dest), max(idx_int2, idx_dest)
                                valid_split_stations.update(seq2_list[s2+1:e2])
                                
                                # 🌟 FIX: Find the original mixed-case station name instead of the ALL CAPS version!
                                original_case_interchange = seq2_list[idx_int2]
                                valid_split_stations.add(original_case_interchange)
                        
                                # Also include the interchange station itself as a valid split point!
                                valid_split_stations.add(interchange)

        # Clean up any potential casing duplicates across the entire pool
        valid_split_stations = {s.strip().title().replace(" And ", " & ").replace("(Hants)", "(Hants)").replace("(Dorset)", "(Dorset)").replace("(London)", "(London)") for s in valid_split_stations}
        #  PRODUCT MIX MODIFICATION 
        # Opened up from a single code restriction to allow full tier composition matching
        filtered_df = df[df['TICKET_CODE'].isin(ticket_filter)]
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
            st.info("No valid line-of-route splits found for this ticket code tier.")
            
# --- 4. DATA TABLE VIEW ---
with st.expander("View Raw Fare Data"):
    st.dataframe(df[(df['ORIGIN_CLEAN'] == origin) | (df['DEST_CLEAN'] == destination)])
