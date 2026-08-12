"""Product identity: every user-visible name, in one place.

Renaming the product is a one-line change here. Nothing else in the codebase
should hard-code the name, the descriptor or the sign-in palette.

The sign-in surface has its own palette because it sits on a dark ground, where
the application's light-mode greens and ambers go muddy. The accent pair is
deliberately the same one core.ui uses, so the cover and the application read as
one product.
"""

# --------------------------------------------------------------------------
# Naming
# --------------------------------------------------------------------------
SUITE = "CISCLD"
PRODUCT = "Ascend"

NAME = f"{SUITE} {PRODUCT}"
DESCRIPTOR = "On-prem to cloud decision simulator"
PAGE_TITLE = f"{NAME} - {DESCRIPTOR}"
PAGE_ICON = ":material/cloud_sync:"

THESIS = ("A migration business case you can defend line by line "
          "&mdash; including the parts that argue against moving.")

FOOTNOTE = ("Priced live against the Azure Retail Prices API and the public AWS "
            "rate feed. A decision aid, not a quotation.")


# --------------------------------------------------------------------------
# The reference-estate readout shown on the sign-in cover
#
# (act, figure, unit, what it means). The act is the stage of core.ui.NARRATIVE
# that produces the figure, so the label carries real information rather than
# decorating the row with a number.
#
# Every figure below is an output of this model against the 547-VM reference
# estate, not a vendor claim.
# --------------------------------------------------------------------------
READOUT = [
    ("Discover", "547", "VMs in the reference estate",
     "Sixty per cent Windows, forty per cent Linux, profiled in full before a "
     "single number is quoted."),
    ("Decide", "$0.0460", "per vCPU hour, on Azure and on AWS alike",
     "Both charge the same for licence-included Windows compute. The Azure case "
     "is Hybrid Benefit and free ESU, not cheaper cores."),
    ("Execute", "46%", "of the estate Azure Migrate carries end to end",
     "And no database of any kind. The remainder needs tooling you have to "
     "choose, buy and staff."),
    ("Assess", "16%", "of vCPU that right-sizing actually returns",
     "A 1.3x comfort factor and discrete SKU sizes eat the rest. Cases built on "
     "30 to 40 per cent do not survive the price list."),
]


# --------------------------------------------------------------------------
# Sign-in palette (dark ground)
# --------------------------------------------------------------------------
VOID = "#080C17"          # page base, cool slate rather than black
PLATE = "#0E1426"         # panels and the manifest field
RULE = "rgba(150,170,215,.155)"
ACCENT = "#3B6FD4"        # same signal blue as core.ui
ACCENT_2 = "#7A5BC4"
LIVE = "#3FBF83"          # positive, lifted for the dark ground
PAPER = "#E8EDF7"
PAPER_DIM = "rgba(232,237,247,.58)"

FONT_SANS = "'IBM Plex Sans', 'Segoe UI', system-ui, -apple-system, sans-serif"
FONT_MONO = "'IBM Plex Mono', ui-monospace, 'Cascadia Mono', Consolas, monospace"
