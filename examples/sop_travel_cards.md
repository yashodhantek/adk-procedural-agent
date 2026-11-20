# Travel desk SOP (procedure cards)

## Term: UV index
Kind: concept
Aliases: uv, sun strength, sunburn risk
Definition: WHO UV index; 0-2 low, 3-5 moderate, 6-7 high, 8-10 very high, 11+ extreme.
Related: get_uv_index

## Term: latitude
Kind: parameter
Aliases: lat_deg, lat_degrees
Definition: Our older SOPs call latitude lat_deg.

## Procedure: get_uv_index
Description: Today's maximum UV index for a city, to advise on sun protection.
Domain: weather
Inputs: lat_deg, lng
Outputs: uv_index_max
Needs: geocode_city (lat_deg->latitude, lng->longitude)
API: GET https://api.open-meteo.com/v1/forecast?latitude={lat_deg}&longitude={lng}&daily=uv_index_max&timezone=auto&forecast_days=1
Extract: uv_index_max = daily.uv_index_max.0
Required: uv_index_max
Sample: lat_deg=17.38; lng=78.46
Steps:
1. Geocode the city.
2. Read today's max UV index.
3. Advise sunscreen from 3 upwards.

## Procedure: travel_budget_in_inr
Description: Total trip budget converted to rupees.
Domain: finance
Inputs: amount, rate
Outputs: budget_inr
Compute: budget_inr = round(amount * rate * 1.05, 2)
Steps:
1. Get the exchange rate for the traveller's currency to INR.
2. Add a 5% card-fee buffer.

## Procedure: beach_day_check
Description: Bundle for "is it a good beach day": conditions brief plus UV.
Domain: weather
Inputs: city
Made of: city_conditions_brief, get_uv_index
Steps:
1. Run the conditions brief and the UV check.
2. Say go / no-go with the reasons.
