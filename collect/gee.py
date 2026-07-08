import ee
import os
from dotenv import load_dotenv

load_dotenv()

def initialize_ee():
    try:
        # Initialize the Earth Engine module
        ee.Initialize(project=os.environ.get('GEE_PROJECT'))
        print("Earth Engine initialized successfully.")
    except Exception as e:
        print(f"An error occurred while initializing Earth Engine: {e}")

# Call the function to initialize Earth Engine
initialize_ee()