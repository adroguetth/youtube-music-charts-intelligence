# 🎬 Script 3 — Chart Data Enrichment, Three-Layer YouTube Metadata

![MIT License](https://img.shields.io/badge/license-MIT-9ecae1?style=flat-square&logo=open-source-initiative&logoColor=white)
![ETL](https://img.shields.io/badge/ETL-9ecae1?style=flat-square)
![Data Enrichment](https://img.shields.io/badge/Data-Enrichment-blue?style=flat-square)
![Metadata](https://img.shields.io/badge/Metadata-YouTube-red?style=flat-square&logo=youtube&logoColor=white)
![Three Layers](https://img.shields.io/badge/Fallback-3%20layers-orange?style=flat-square)
![YouTube Charts](https://img.shields.io/badge/YouTube-Charts-FF0000?style=flat-square&logo=youtube&logoColor=white) 




![No AI](https://img.shields.io/badge/AI-none-lightgrey?style=flat-square)
![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-07405e?style=flat-square&logo=sqlite&logoColor=white)
![YouTube Data API](https://img.shields.io/badge/YouTube-Data%20API%20v3-FF0000?style=flat-square&logo=youtube&logoColor=white)
![yt-dlp](https://img.shields.io/badge/yt--dlp-4E4E4E?style=flat-square)
![Selenium](https://img.shields.io/badge/Selenium-43B02A?style=flat-square&logo=selenium&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub-Actions-2088FF?style=flat-square&logo=github-actions&logoColor=white)

> **Pipeline position:** `1_download_chart` → `2_1_country_genre` → `2_2_song_catalog` → **`3_enrich_chart_data`** → `4_notebooks` → `5_export`
>
> **Execution model:** local Linux host or GitHub Actions. The package is environment-driven: `YOUTUBE_API_KEY` enables the API layer, and `GITHUB_ACTIONS=true` suppresses the interactive prompt.
>
> **Documentation style:** follows `README Script 1.md` (stage 1) and `README Script 2.2.md` (stage 2.2).
>
> **This stage uses no AI, no prompts, no model calls, and no mandatory secrets.** The only optional secret is a YouTube Data API v3 key.
