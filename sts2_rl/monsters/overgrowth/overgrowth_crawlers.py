from __future__ import annotations

from ..base import Encounter
from .shrinker_beetle import ShrinkerBeetle
from .fuzzy_wurm_crawler import FuzzyWurmCrawler

OVERGROWTH_CRAWLERS_NORMAL = Encounter(
    id="overgrowth_crawlers_normal",
    monster_classes=[ShrinkerBeetle, FuzzyWurmCrawler],
    # C# class OvergrowthCrawlers — no tier suffix, unlike the sim id.
    entry_slug="OVERGROWTH_CRAWLERS",
)
