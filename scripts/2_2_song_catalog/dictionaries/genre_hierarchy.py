"""
Genre Hierarchy - Country to Genre Priorities
============================================================================
Static dictionary that defines the ordered list of most likely macro-genres
for each country. Used by the collaboration weight algorithm to infer a
genre when artist-level genre data is missing or when there is a tie.

The list is ordered from most to least culturally dominant. The resolver
walks this list from top to bottom to find the first genre that is present
in the known artist genres for that country.

IMPORTANT:
    The genre names in this file MUST match the macro-genres defined in
    `scripts/2_1_country_genre/dictionaries/genres.py`. Mismatches
    will cause the resolver to fall back to `DEFAULT_GENRE` (Pop).

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from typing import Dict, List

# ============================================================================
# GENRE HIERARCHY BY COUNTRY
# ============================================================================

GENRE_HIERARCHY: Dict[str, List[str]] = {
    # ========================================================================
    # NORTH AMERICA
    # ========================================================================
    "United States": [
        "Pop", "Hip-Hop/Rap", "R&B/Soul", "Country", "Rock",
        "Alternative", "Electrónica/Dance", "Reggaetón/Trap Latino",
        "Jazz/Blues", "Classical"
    ],
    "Canada": [
        "Pop", "Hip-Hop/Rap", "Rock", "Alternative",
        "Electrónica/Dance", "R&B/Soul", "Reggaetón/Trap Latino",
        "Country", "Classical"
    ],
    "Mexico": [
        "Regional Mexicano", "Reggaetón/Trap Latino", "Pop",
        "Bachata", "Cumbia", "Rock", "Tropical/Salsa/Merengue/Bolero",
        "Classical"
    ],

    # ========================================================================
    # CENTRAL AMERICA & CARIBBEAN
    # ========================================================================
    "Guatemala": ["Reggaetón/Trap Latino", "Bachata", "Cumbia", "Dancehall/Reggae", "Tropical/Salsa/Merengue/Bolero"],
    "Honduras": ["Reggaetón/Trap Latino", "Bachata", "Cumbia", "Dancehall/Reggae", "Tropical/Salsa/Merengue/Bolero"],
    "El Salvador": ["Reggaetón/Trap Latino", "Bachata", "Cumbia", "Dancehall/Reggae"],
    "Nicaragua": ["Reggaetón/Trap Latino", "Bachata", "Cumbia", "Dancehall/Reggae"],
    "Costa Rica": ["Reggaetón/Trap Latino", "Pop", "Bachata", "Cumbia", "Dancehall/Reggae", "Tropical/Salsa/Merengue/Bolero"],
    "Panama": ["Reggaetón/Trap Latino", "Dancehall/Reggae", "Tropical/Salsa/Merengue/Bolero", "Cumbia", "Pop"],
    "Belize": ["Dancehall/Reggae", "Reggaetón/Trap Latino", "Pop", "Cumbia"],
    "Jamaica": ["Dancehall/Reggae"],
    "Puerto Rico": ["Reggaetón/Trap Latino", "Pop"],
    "Dominican Republic": ["Reggaetón/Trap Latino", "Bachata", "Tropical/Salsa/Merengue/Bolero", "Dancehall/Reggae"],
    "Cuba": ["Reggaetón/Trap Latino", "Tropical/Salsa/Merengue/Bolero", "Pop", "Jazz/Blues"],
    "Haiti": ["Reggaetón/Trap Latino", "Tropical/Salsa/Merengue/Bolero", "Pop"],
    "Trinidad and Tobago": ["Tropical/Salsa/Merengue/Bolero", "Dancehall/Reggae", "Reggaetón/Trap Latino", "Pop"],
    "Bahamas": ["Pop", "Dancehall/Reggae", "R&B/Soul"],
    "Barbados": ["Pop", "Dancehall/Reggae", "R&B/Soul", "Reggaetón/Trap Latino"],
    "Saint Lucia": ["Pop", "Dancehall/Reggae", "Reggaetón/Trap Latino"],
    "Grenada": ["Pop", "Dancehall/Reggae", "Reggaetón/Trap Latino"],
    "Saint Vincent and the Grenadines": ["Pop", "Dancehall/Reggae", "Reggaetón/Trap Latino"],
    "Antigua and Barbuda": ["Pop", "Dancehall/Reggae", "Reggaetón/Trap Latino"],
    "Dominica": ["Pop", "Dancehall/Reggae", "Reggaetón/Trap Latino"],
    "Saint Kitts and Nevis": ["Pop", "Dancehall/Reggae", "Reggaetón/Trap Latino"],

    # ========================================================================
    # SOUTH AMERICA
    # ========================================================================
    "Colombia": ["Reggaetón/Trap Latino", "Cumbia", "Vallenato", "Tropical/Salsa/Merengue/Bolero", "Pop", "Rock"],
    "Venezuela": ["Reggaetón/Trap Latino", "Tropical/Salsa/Merengue/Bolero", "Pop", "Rock", "Classical"],
    "Ecuador": ["Reggaetón/Trap Latino", "Cumbia", "Folklore/Raíces", "Pop"],
    "Peru": ["Reggaetón/Trap Latino", "Cumbia", "Folklore/Raíces", "Pop"],
    "Bolivia": ["Reggaetón/Trap Latino", "Cumbia", "Folklore/Raíces", "Pop"],
    "Chile": ["Reggaetón/Trap Latino", "Cumbia", "Pop", "Rock", "Folklore/Raíces", "Classical"],
    "Argentina": ["Reggaetón/Trap Latino", "Cumbia", "Rock", "Pop", "Folklore/Raíces", "Classical"],
    "Paraguay": ["Reggaetón/Trap Latino", "Cumbia", "Folklore/Raíces", "Pop"],
    "Uruguay": ["Reggaetón/Trap Latino", "Cumbia", "Pop", "Rock", "Electrónica/Dance", "Classical"],
    "Brazil": ["Brazilian Regional", "Funk Brasileiro", "Reggaetón/Trap Latino", "Pop", "Rock", "Hip-Hop/Rap", "Classical"],
    "Guyana": ["Dancehall/Reggae", "Reggaetón/Trap Latino", "Pop"],
    "Suriname": ["Dancehall/Reggae", "Reggaetón/Trap Latino", "Pop"],
    "French Guiana": ["Dancehall/Reggae", "Reggaetón/Trap Latino", "Pop", "Kizomba/Zouk"],

    # ========================================================================
    # WESTERN EUROPE
    # ========================================================================
    "Spain": ["Reggaetón/Trap Latino", "Pop", "Hip-Hop/Rap", "Flamenco / Copla", "Rock", "Electrónica/Dance", "Classical"],
    "Portugal": ["Pop", "Hip-Hop/Rap", "Folklore/Raíces", "Kizomba/Zouk", "Reggaetón/Trap Latino", "Rock", "Classical"],
    "United Kingdom": ["Pop", "Hip-Hop/Rap", "Rock", "Alternative", "Electrónica/Dance", "Afrobeats", "Dancehall/Reggae", "R&B/Soul", "Classical"],
    "Ireland": ["Pop", "Rock", "Alternative", "Hip-Hop/Rap", "Folklore/Raíces", "Electrónica/Dance", "Classical"],
    "France": ["Pop", "Hip-Hop/Rap", "Electrónica/Dance", "Afrobeats", "Chanson", "R&B/Soul", "Rock", "Classical"],
    "Belgium": ["Pop", "Hip-Hop/Rap", "Electrónica/Dance", "Rock", "Chanson", "Classical"],
    "Netherlands": ["Pop", "Electrónica/Dance", "Hip-Hop/Rap", "Rock", "Alternative", "Classical"],
    "Germany": ["Hip-Hop/Rap", "Pop", "Electrónica/Dance", "Schlager", "Rock", "Alternative", "Classical"],
    "Austria": ["Pop", "Hip-Hop/Rap", "Schlager", "Rock", "Alpine Folk", "Classical"],
    "Switzerland": ["Pop", "Hip-Hop/Rap", "Alpine Folk", "Rock", "Electrónica/Dance", "Schlager", "Classical"],
    "Italy": ["Pop", "Hip-Hop/Rap", "Canzone Italiana", "Rock", "Electrónica/Dance", "Classical"],
    "Greece": ["Pop", "Hip-Hop/Rap", "Laïko", "Rock", "Electrónica/Dance", "Classical"],
    "Sweden": ["Pop", "Hip-Hop/Rap", "Electrónica/Dance", "Rock", "Metal", "Dansband", "Classical"],
    "Norway": ["Pop", "Hip-Hop/Rap", "Metal", "Electrónica/Dance", "Rock", "Dansband", "Classical"],
    "Denmark": ["Pop", "Hip-Hop/Rap", "Electrónica/Dance", "Rock", "Dansband", "Classical"],
    "Finland": ["Pop", "Metal", "Hip-Hop/Rap", "Rock", "Iskelmä", "Electrónica/Dance", "Classical"],
    "Iceland": ["Pop", "Alternative", "Rock", "Hip-Hop/Rap", "Electrónica/Dance", "Classical"],

    # ========================================================================
    # EASTERN EUROPE & BALKANS
    # ========================================================================
    "Russia": ["Pop", "Hip-Hop/Rap", "Rock", "Electrónica/Dance", "Classical", "Folklore/Raíces"],
    "Ukraine": ["Pop", "Hip-Hop/Rap", "Rock", "Electrónica/Dance", "Folklore/Raíces"],
    "Poland": ["Pop", "Hip-Hop/Rap", "Rock", "Electrónica/Dance", "Classical"],
    "Czech Republic": ["Pop", "Hip-Hop/Rap", "Rock", "Electrónica/Dance", "Classical"],
    "Slovakia": ["Pop", "Hip-Hop/Rap", "Rock"],
    "Hungary": ["Pop", "Hip-Hop/Rap", "Rock", "Electrónica/Dance", "Classical"],
    "Romania": ["Manele", "Pop", "Hip-Hop/Rap", "Electrónica/Dance", "Rock"],
    "Bulgaria": ["Chalga", "Pop", "Hip-Hop/Rap", "Rock", "Electrónica/Dance"],
    "Serbia": ["Turbo-folk", "Pop", "Hip-Hop/Rap", "Electrónica/Dance", "Rock"],
    "Croatia": ["Pop", "Turbo-folk", "Rock", "Hip-Hop/Rap", "Electrónica/Dance"],
    "Bosnia and Herzegovina": ["Turbo-folk", "Pop", "Rock", "Hip-Hop/Rap"],
    "Montenegro": ["Turbo-folk", "Pop", "Rock"],
    "North Macedonia": ["Turbo-folk", "Pop", "Rock"],
    "Kosovo": ["Tallava", "Pop", "Hip-Hop/Rap", "Turbo-folk", "Rock"],
    "Albania": ["Tallava", "Pop", "Hip-Hop/Rap", "Rock"],
    "Slovenia": ["Pop", "Rock", "Hip-Hop/Rap", "Electrónica/Dance"],
    "Lithuania": ["Pop", "Hip-Hop/Rap", "Rock", "Electrónica/Dance"],
    "Latvia": ["Pop", "Hip-Hop/Rap", "Rock", "Electrónica/Dance"],
    "Estonia": ["Pop", "Hip-Hop/Rap", "Rock", "Electrónica/Dance", "Folklore/Raíces"],
    "Belarus": ["Pop", "Rock", "Hip-Hop/Rap"],
    "Moldova": ["Pop", "Rock", "Hip-Hop/Rap", "Manele"],

    # ========================================================================
    # MIDDLE EAST & NORTH AFRICA
    # ========================================================================
    "Turkey": ["Turkish Pop/Rock", "Pop", "Hip-Hop/Rap", "Rock", "Arabesk", "Classical"],
    "Israel": ["Israeli Pop/Rock", "Pop", "Hip-Hop/Rap", "Rock", "Mizrahi", "Classical"],
    "Lebanon": ["Arabic Pop/Rock", "Pop", "Hip-Hop/Rap"],
    "Syria": ["Arabic Pop/Rock"],
    "Jordan": ["Arabic Pop/Rock", "Pop", "Hip-Hop/Rap"],
    "Iraq": ["Arabic Pop/Rock", "Pop", "Hip-Hop/Rap"],
    "Iran": ["Pop", "Hip-Hop/Rap", "Rock", "Classical"],
    "Egypt": ["Arabic Pop/Rock", "Shaabi", "Hip-Hop/Rap"],
    "Morocco": ["Arabic Pop/Rock", "Gnawa", "Hip-Hop/Rap"],
    "Algeria": ["Arabic Pop/Rock", "Hip-Hop/Rap", "Raï"],
    "Tunisia": ["Arabic Pop/Rock", "Hip-Hop/Rap"],
    "Libya": ["Arabic Pop/Rock"],
    "Saudi Arabia": ["Arabic Pop/Rock", "Hip-Hop/Rap", "Khaliji"],
    "United Arab Emirates": ["Arabic Pop/Rock", "Hip-Hop/Rap", "Khaliji"],
    "Kuwait": ["Arabic Pop/Rock", "Hip-Hop/Rap", "Khaliji"],
    "Qatar": ["Arabic Pop/Rock", "Hip-Hop/Rap", "Khaliji"],
    "Bahrain": ["Arabic Pop/Rock", "Khaliji"],
    "Oman": ["Arabic Pop/Rock", "Khaliji"],
    "Yemen": ["Arabic Pop/Rock"],

    # ========================================================================
    # SUB-SAHARAN AFRICA
    # ========================================================================
    "Nigeria": ["Afrobeats", "Hip-Hop/Rap", "Jùjú", "Fuji"],
    "Ghana": ["Afrobeats", "Highlife", "Hip-Hop/Rap"],
    "South Africa": ["Amapiano", "Kwaito", "Hip-Hop/Rap", "Afrobeats", "Electrónica/Dance", "Maskandi", "Mbaqanga", "Afro-soul"],
    "Tanzania": ["Bongo Flava", "Taarab", "Afrobeats", "Hip-Hop/Rap"],
    "Kenya": ["Afrobeats", "Gengetone", "Kapuka", "Benga", "Hip-Hop/Rap"],
    "Uganda": ["Afrobeats", "Hip-Hop/Rap"],
    "Zimbabwe": ["Zim Dancehall", "Afrobeats", "Amapiano"],
    "Zambia": ["Amapiano", "Afrobeats", "Hip-Hop/Rap"],
    "Mozambique": ["Marrabenta", "Amapiano", "Afrobeats", "Kizomba/Zouk"],
    "Angola": ["Kuduro", "Kizomba/Zouk", "Afrobeats"],
    "Ethiopia": ["Ethio-jazz", "Pop", "Hip-Hop/Rap"],
    "Rwanda": ["Afrobeats", "Hip-Hop/Rap"],
    "Senegal": ["Mbalax", "Afrobeats", "Hip-Hop/Rap"],
    "Mali": ["Afrobeats"],
    "Ivory Coast": ["Coupé-Décalé", "Afrobeats", "Hip-Hop/Rap"],
    "Cameroon": ["Afrobeats", "Hip-Hop/Rap"],
    "Benin": ["Afrobeats"],
    "Togo": ["Afrobeats"],
    "Burkina Faso": ["Afrobeats"],
    "Niger": ["Afrobeats"],
    "Chad": ["Afrobeats"],
    "Central African Republic": ["Afrobeats"],
    "Equatorial Guinea": ["Afrobeats"],
    "Gabon": ["Afrobeats"],
    "Republic of the Congo": ["Soukous/Ndombolo", "Afrobeats"],
    "Democratic Republic of the Congo": ["Soukous/Ndombolo", "Afrobeats"],
    "Burundi": ["Afrobeats"],
    "Djibouti": ["Afrobeats"],
    "Eritrea": ["Afrobeats"],
    "Somalia": ["Afrobeats"],
    "Sudan": ["Afrobeats", "Hip-Hop/Rap"],
    "South Sudan": ["Afrobeats"],
    "Malawi": ["Afrobeats"],
    "Botswana": ["Afrobeats", "Amapiano"],
    "Namibia": ["Afrobeats", "Amapiano"],
    "Lesotho": ["Afrobeats", "Amapiano"],
    "Eswatini": ["Afrobeats", "Amapiano"],
    "Madagascar": ["Afrobeats"],
    "Comoros": ["Afrobeats", "Taarab"],
    "Mauritius": ["Afrobeats", "Kizomba/Zouk"],
    "Seychelles": ["Afrobeats", "Kizomba/Zouk"],
    "Cabo Verde": ["Kizomba/Zouk", "Coladeira", "Funaná"],
    "São Tomé and Príncipe": ["Afrobeats", "Kizomba/Zouk"],

    # ========================================================================
    # ASIA
    # ========================================================================
    "India": ["Indian Pop", "Hip-Hop/Rap", "Rock", "Electrónica/Dance"],
    "Pakistan": ["Pakistani Pop", "Hip-Hop/Rap", "Rock"],
    "Bangladesh": ["Bangladeshi Pop/Rock", "Hip-Hop/Rap"],
    "Sri Lanka": ["Sri Lankan Pop/Rock", "Hip-Hop/Rap"],
    "Nepal": ["Nepali Pop/Rock", "Hip-Hop/Rap"],
    "Bhutan": ["Bhutanese Pop/Rock"],
    "Maldives": ["Maldivian Pop/Rock"],
    "South Korea": ["K-Pop/K-Rock", "Hip-Hop/Rap", "Rock", "Classical"],
    "Japan": ["J-Pop/J-Rock", "Hip-Hop/Rap", "Rock", "Electrónica/Dance", "Classical"],
    "China": ["C-Pop/C-Rock", "Hip-Hop/Rap", "Rock", "Classical"],
    "Taiwan": ["TW-Pop/TW-Rock", "Hip-Hop/Rap", "Rock", "Classical"],
    "Hong Kong": ["HK-Pop/HK-Rock", "Hip-Hop/Rap", "Classical"],
    "Macau": ["Macanese Pop/Rock", "Pop"],
    "Mongolia": ["Mongolian Pop/Rock/Metal", "Hip-Hop/Rap"],
    "Indonesia": ["Indonesian Pop/Dangdut", "Rock", "Hip-Hop/Rap", "Electrónica/Dance"],
    "Malaysia": ["Malaysian Pop", "Indonesian Pop/Dangdut", "K-Pop/K-Rock", "Hip-Hop/Rap"],
    "Singapore": ["Singaporean Pop", "K-Pop/K-Rock", "C-Pop/C-Rock", "Hip-Hop/Rap"],
    "Philippines": ["OPM", "K-Pop/K-Rock", "Pop", "Rock", "Hip-Hop/Rap"],
    "Thailand": ["T-Pop/T-Rock", "K-Pop/K-Rock", "Hip-Hop/Rap"],
    "Vietnam": ["V-Pop/V-Rock", "K-Pop/K-Rock", "Hip-Hop/Rap"],
    "Myanmar": ["Burmese Pop/Rock", "Hip-Hop/Rap"],
    "Cambodia": ["Cambodian Pop/Rock", "Hip-Hop/Rap"],
    "Laos": ["Lao Pop/Rock", "Hip-Hop/Rap"],
    "Brunei": ["Bruneian Pop/Rock", "Malaysian Pop"],
    "Timor-Leste": ["Timorese Pop/Rock", "Dancehall/Reggae"],

    # ========================================================================
    # CENTRAL ASIA & CAUCASUS
    # ========================================================================
    "Kazakhstan": ["Q-pop/Q-rock", "Pop", "Hip-Hop/Rap"],
    "Uzbekistan": ["Pop", "Hip-Hop/Rap"],
    "Turkmenistan": ["Pop"],
    "Kyrgyzstan": ["Pop", "Hip-Hop/Rap"],
    "Tajikistan": ["Pop"],
    "Azerbaijan": ["Pop", "Hip-Hop/Rap", "Rock"],
    "Georgia": ["Pop", "Hip-Hop/Rap", "Rock"],
    "Armenia": ["Pop", "Hip-Hop/Rap", "Rock", "Classical"],

    # ========================================================================
    # OCEANIA
    # ========================================================================
    "Australia": ["Pop", "Hip-Hop/Rap", "Rock", "Alternative", "Electrónica/Dance", "Country", "Aboriginal Australian Pop/Rock", "Classical"],
    "New Zealand": ["Pop", "Hip-Hop/Rap", "Rock", "Alternative", "Māori Pop/Rock", "Electrónica/Dance", "Classical"],
    "Papua New Guinea": ["PNG Pop/Rock", "Dancehall/Reggae"],
    "Fiji": ["Pasifika Pop/Rock", "Dancehall/Reggae"],
    "Samoa": ["Pasifika Pop/Rock", "Dancehall/Reggae"],
    "Tonga": ["Pasifika Pop/Rock", "Dancehall/Reggae"],
    "Solomon Islands": ["Pasifika Pop/Rock"],
    "Vanuatu": ["Pasifika Pop/Rock"],
    "Micronesia": ["Pasifika Pop/Rock"],
    "Marshall Islands": ["Pasifika Pop/Rock"],
    "Palau": ["Pasifika Pop/Rock"],
    "Nauru": ["Pasifika Pop/Rock"],
    "Kiribati": ["Pasifika Pop/Rock"],
    "Tuvalu": ["Pasifika Pop/Rock"],
    "Hawaii": ["Hawaiian Pop/Rock", "Pop", "Dancehall/Reggae"],
}

# Safe defaults when no country data is available
DEFAULT_GENRE: str = "Pop"
DEFAULT_COUNTRY: str = "Unknown"

# ============================================================================
# PUBLIC API
# ============================================================================
__all__ = ["GENRE_HIERARCHY", "DEFAULT_GENRE", "DEFAULT_COUNTRY"]
