# For OAuth, use https://oauthlib.readthedocs.io/en/latest/installation.html
# Install the library!
from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session
from datetime import datetime, timedelta, timezone
import math, argparse

# OAuth API settings (you must register)
# https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings
client_id = ""
client_secret = ""

if len(client_id) == 0 or len(client_secret) == 0:
    print("Fill in client_id and client_secret for OAuth authentication!")
    print("Create a free account at Copernicus and go here: https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings")
    exit()

# Default values
HEIGHT = 512 # Default image height
MAX_WIDTH = 2500 # Maximum allowed image width by the API
FORMAT = "image/jpeg" # Output data format
FILENAME = "image1.jpg" # Output file
QUALITY = 90 # JPEG quality
BOX = "15.0617, 50.2856, 15.2252, 50.3378" # GPS coordinates of a square over Prague

# Evalscript is a special processing JavaScript executed on the Copernicus servers
# We want satellite data in true colors (bands B02, B03, B04)
# Increase exposure because raw data is quite dark
EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: ["B02", "B03", "B04"],
    output: { bands: 3 },
  }
}
function evaluatePixel(sample) {
  let exposure = 2;
  return [sample.B04 * exposure, sample.B03 * exposure, sample.B02 * exposure];
}
"""

parser = argparse.ArgumentParser()
parser.add_argument("-S", "--soubor", default=FILENAME, type=str, help = "File name (prague.jpg etc.)")
parser.add_argument("-V", "--vyska", default=HEIGHT, type=int, help = "Image height in pixels (500, 1000 etc.)")
parser.add_argument("-B", "--box", default=BOX, type=str, help = "Bounding box in WGS84 coordinates (lng0,lat0,lng1,lat1)")
parser.add_argument("-F", "--format", default=FORMAT, type=str, help = "Image format (image/jpeg, image/png)")
parser.add_argument("-K", "--kvalita", default=QUALITY, type=int, help = "Image quality (0-100)")
parser.add_argument("-E", "--evalscript", default="", type=str, help = "File with custom evalscript (evalscript.js)")
parser.add_argument("-J", "--jas", default=2, type=float, help = "Image brightness if built-in evalscript is used (0-XXX)")
parser.add_argument("-T", "--ukaztoken", action="store_true", help = "Only generates a temporary token/API key (can be used for Bearer authentication without OAuth)")
args = parser.parse_args()

# Modify parameters based on script arguments
HEIGHT = args.vyska
FORMAT = args.format
FILENAME = args.soubor
QUALITY = args.kvalita
BOX = [float(coord) for coord in args.box.split(",")]
EVALSCRIPT = EVALSCRIPT.replace("let exposure = 2;", f"let exposure = {args.jas};")

# If a custom evalscript file is specified, replace the default one
if len(args.evalscript) > 1:
    try:
        with open(args.evalscript, "r") as f:
            EVALSCRIPT = f.read()
    except:
        print(f"Cannot read evalscript {args.evalscript}. Using default")

# Create an OAuth session
client = BackendApplicationClient(client_id=client_id)
oauth = OAuth2Session(client=client)
token = oauth.fetch_token(token_url='https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token', client_secret=client_secret, include_client_id=True)

# If we only want to print the token/API key for Bearer authentication
# Print the authentication values and exit the program
if args.ukaztoken:
    for key in token:
        print(f"{key}: {token[key]}")
    exit()

# Calculate aspect ratio for the image in pixels from geographic coordinates
# Potentially imprecise, but good enough for general use, not for geodesy or GIS
lat_diff = BOX[3] - BOX[1]
lng_diff = BOX[2] - BOX[0]
avg_lat = (BOX[1] + BOX[3]) / 2
lat_distance = lat_diff * 111
lng_distance = lng_diff * 111 * math.cos(math.radians(avg_lat))
aspect_ratio = lng_distance / lat_distance

# Calculate image width based on height and aspect ratio
width = int(HEIGHT * aspect_ratio)
height = HEIGHT

# API allows images with width of at most 2500 pixels
# So if we calculated a larger width, reduce the height
if width > MAX_WIDTH:
    width = MAX_WIDTH
    height = int(width / aspect_ratio)
print(f"Final image dimensions: {width}x{height} pixels")

# The satellite usually passes over the selected area in Europe every 2-3 days,
# but the delay can be longer, so set the search range to 7 days
end_date = datetime.now(timezone.utc)
start_date = (end_date - timedelta(days=7)).isoformat()
end_date = end_date.isoformat()

# Prepare the API request in JSON format
# We want an image from Sentinel-2 L2A satellite
# For the given box, pixel size, format, etc.
# For more parameters see https://shapps.dataspace.copernicus.eu/requests-builder/
request_params = {
    "input": {
        "bounds": {
            "bbox": BOX
        },
        "data": [
            {
                "type": "sentinel-2-l2a",
                "dataFilter": {
                    "timeRange": {
                        "from": start_date,
                        "to": end_date,
                    }
                },
                "processing": {
                    "upsampling": "BILINEAR",
                    "downsampling": "BILINEAR"
                },
            }
        ]
    },
    "output": {
        "width": width,
        "height": height,
        "responses": [
            {
                "identifier": "default",
                "format": {
                    "type": FORMAT,
                    "quality": QUALITY,
                }
            }
        ]
    },
    "evalscript": EVALSCRIPT
}

# Perform an authenticated HTTP request via OAuth and the server should return raw image bytes

# In this API response, we (probably) won't find out the exact acquisition time of the image
response = oauth.post("https://sh.dataspace.copernicus.eu/api/v1/process", json = request_params)
if response.status_code == 200:
    print(f"Saving image {FILENAME}")
    with open(FILENAME, "wb") as file:
        file.write(response.content)
else:
    print(f"An error occurred!\nHTTP code: {response.status_code}\n{response.text}")

