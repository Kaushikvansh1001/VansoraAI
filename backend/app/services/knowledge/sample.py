"""Prepared text for hosted demo mode.

The hosted API searches these passages with Postgres full-text search.
It does not embed them and it does not call them a vector search.
"""

SAMPLE_FILENAME = "Northwind Studio sample.txt"

SAMPLE_CHUNKS = (
    "Northwind Studio is a small furniture workshop in Portland. It sells lamps, tables, and chairs to retailers.",
    "In 2024 Northwind Studio revenue was 480000 dollars. The West region produced the most revenue.",
    "The best selling product was the Oak Lamp, with 1200 units sold in 2024.",
    "Returns were 3 percent of orders. The studio ships in-stock furniture within 5 business days.",
)

SAMPLE_TEXT = "\n\n".join(SAMPLE_CHUNKS)
