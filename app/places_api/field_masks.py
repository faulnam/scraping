"""
Google Places API (New) Field Mask definitions.
Setting explicit field masks is essential to minimize API costs and fetch only required data.
"""

# Search stage: Basic tier (cost-efficient)
SEARCH_FIELD_MASK = "places.id,places.displayName,places.formattedAddress,places.location,places.primaryType"

# Details stage: Enterprise tier (invoked selectively for new or expired place_ids only)
PLACE_DETAILS_FIELD_MASK = "id,displayName,formattedAddress,nationalPhoneNumber,websiteUri,rating,userRatingCount,regularOpeningHours,businessStatus,googleMapsUri,location"
