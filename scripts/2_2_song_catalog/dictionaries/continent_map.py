"""
Continent Mapping - Country to Continent Resolution
============================================================================
Static dictionary that maps country names to their corresponding continent.
Used by the collaboration weight algorithm to resolve multi-artist tracks
when the artists are from the same continent but different countries.

This module is intentionally kept as pure data (no logic) so it can be
updated independently of the codebase. It covers all countries present in
the YouTube Charts global database.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from typing import Dict

# ============================================================================
# COUNTRY TO CONTINENT MAPPING
# ============================================================================
# Keys are canonical country names (as they appear in artist_countries_genres.db).
# Values are continent labels used for grouping in the collaboration resolver.
#
# Continents used:
#   - "Asia"
#   - "America"  (covers North, Central, South America and the Caribbean)
#   - "Europe"
#   - "Africa"
#   - "Oceania"

COUNTRY_TO_CONTINENT: Dict[str, str] = {
    # ========================================================================
    # ASIA
    # ========================================================================
    "South Korea": "Asia",
    "Japan": "Asia",
    "China": "Asia",
    "Taiwan": "Asia",
    "Hong Kong": "Asia",
    "Thailand": "Asia",
    "Vietnam": "Asia",
    "Philippines": "Asia",
    "Indonesia": "Asia",
    "Malaysia": "Asia",
    "Singapore": "Asia",
    "India": "Asia",
    "Pakistan": "Asia",
    "Bangladesh": "Asia",
    "Sri Lanka": "Asia",
    "Nepal": "Asia",
    "Bhutan": "Asia",
    "Maldives": "Asia",
    "Kazakhstan": "Asia",
    "Uzbekistan": "Asia",
    "Turkmenistan": "Asia",
    "Kyrgyzstan": "Asia",
    "Tajikistan": "Asia",
    "Mongolia": "Asia",
    "Myanmar": "Asia",
    "Laos": "Asia",
    "Cambodia": "Asia",
    "Afghanistan": "Asia",
    "Iran": "Asia",
    "Iraq": "Asia",
    "Syria": "Asia",
    "Lebanon": "Asia",
    "Jordan": "Asia",
    "Israel": "Asia",
    "Palestine": "Asia",
    "Saudi Arabia": "Asia",
    "Yemen": "Asia",
    "Oman": "Asia",
    "United Arab Emirates": "Asia",
    "Qatar": "Asia",
    "Kuwait": "Asia",
    "Bahrain": "Asia",
    "Turkey": "Asia",
    "Cyprus": "Asia",
    "Azerbaijan": "Asia",
    "Georgia": "Asia",
    "Armenia": "Asia",
    "Russia": "Asia",  # Transcontinental, but chart-wise usually grouped with Asia
    "Brunei": "Asia",
    "Timor-Leste": "Asia",

    # ========================================================================
    # AMERICA (North, Central, South, Caribbean)
    # ========================================================================
    # North America
    "United States": "America",
    "Canada": "America",
    "Mexico": "America",

    # Central America
    "Guatemala": "America",
    "Honduras": "America",
    "El Salvador": "America",
    "Nicaragua": "America",
    "Costa Rica": "America",
    "Panama": "America",
    "Belize": "America",

    # Caribbean
    "Cuba": "America",
    "Jamaica": "America",
    "Haiti": "America",
    "Dominican Republic": "America",
    "Puerto Rico": "America",
    "Bahamas": "America",
    "Trinidad and Tobago": "America",
    "Barbados": "America",
    "Saint Lucia": "America",
    "Grenada": "America",
    "Saint Vincent and the Grenadines": "America",
    "Antigua and Barbuda": "America",
    "Dominica": "America",
    "Saint Kitts and Nevis": "America",

    # South America
    "Colombia": "America",
    "Venezuela": "America",
    "Ecuador": "America",
    "Peru": "America",
    "Bolivia": "America",
    "Chile": "America",
    "Argentina": "America",
    "Paraguay": "America",
    "Uruguay": "America",
    "Brazil": "America",
    "Guyana": "America",
    "Suriname": "America",
    "French Guiana": "America",

    # ========================================================================
    # EUROPE
    # ========================================================================
    "United Kingdom": "Europe",
    "Ireland": "Europe",
    "France": "Europe",
    "Belgium": "Europe",
    "Netherlands": "Europe",
    "Germany": "Europe",
    "Austria": "Europe",
    "Switzerland": "Europe",  # FIXED: previously "201"
    "Italy": "Europe",
    "Spain": "Europe",
    "Portugal": "Europe",
    "Greece": "Europe",
    "Sweden": "Europe",
    "Norway": "Europe",
    "Denmark": "Europe",
    "Finland": "Europe",
    "Iceland": "Europe",
    "Luxembourg": "Europe",
    "Monaco": "Europe",
    "Liechtenstein": "Europe",
    "Andorra": "Europe",
    "San Marino": "Europe",
    "Malta": "Europe",
    "Poland": "Europe",
    "Czech Republic": "Europe",
    "Slovakia": "Europe",
    "Hungary": "Europe",
    "Romania": "Europe",
    "Bulgaria": "Europe",
    "Serbia": "Europe",
    "Croatia": "Europe",
    "Bosnia and Herzegovina": "Europe",
    "Montenegro": "Europe",
    "North Macedonia": "Europe",
    "Kosovo": "Europe",
    "Albania": "Europe",
    "Slovenia": "Europe",
    "Lithuania": "Europe",
    "Latvia": "Europe",
    "Estonia": "Europe",
    "Belarus": "Europe",
    "Moldova": "Europe",
    "Ukraine": "Europe",

    # ========================================================================
    # AFRICA
    # ========================================================================
    "Nigeria": "Africa",
    "Ghana": "Africa",
    "South Africa": "Africa",
    "Tanzania": "Africa",
    "Kenya": "Africa",
    "Uganda": "Africa",
    "Zimbabwe": "Africa",
    "Zambia": "Africa",
    "Mozambique": "Africa",
    "Angola": "Africa",
    "Ethiopia": "Africa",
    "Rwanda": "Africa",
    "Senegal": "Africa",
    "Mali": "Africa",
    "Ivory Coast": "Africa",
    "Cameroon": "Africa",
    "Benin": "Africa",
    "Togo": "Africa",
    "Burkina Faso": "Africa",
    "Niger": "Africa",
    "Chad": "Africa",
    "Central African Republic": "Africa",
    "Equatorial Guinea": "Africa",
    "Gabon": "Africa",
    "Republic of the Congo": "Africa",
    "Democratic Republic of the Congo": "Africa",
    "Burundi": "Africa",
    "Djibouti": "Africa",
    "Eritrea": "Africa",
    "Somalia": "Africa",
    "Sudan": "Africa",
    "South Sudan": "Africa",
    "Malawi": "Africa",
    "Botswana": "Africa",
    "Namibia": "Africa",
    "Lesotho": "Africa",
    "Eswatini": "Africa",
    "Madagascar": "Africa",
    "Comoros": "Africa",
    "Mauritius": "Africa",
    "Seychelles": "Africa",
    "Cabo Verde": "Africa",
    "São Tomé and Príncipe": "Africa",

    # ========================================================================
    # OCEANIA
    # ========================================================================
    "Australia": "Oceania",
    "New Zealand": "Oceania",
    "Papua New Guinea": "Oceania",
    "Fiji": "Oceania",
    "Samoa": "Oceania",
    "Tonga": "Oceania",
    "Solomon Islands": "Oceania",
    "Vanuatu": "Oceania",
    "Micronesia": "Oceania",
    "Marshall Islands": "Oceania",
    "Palau": "Oceania",
    "Nauru": "Oceania",
    "Kiribati": "Oceania",
    "Tuvalu": "Oceania",
    "Hawaii": "Oceania",
}

# ============================================================================
# PUBLIC API
# ============================================================================
__all__ = ["COUNTRY_TO_CONTINENT"]
