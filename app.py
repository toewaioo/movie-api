from flask import Flask, request, jsonify, abort
from pymongo import MongoClient
from bson.objectid import ObjectId
from bson.errors import InvalidId
from marshmallow import Schema, fields, ValidationError, INCLUDE, EXCLUDE
import datetime
# Import Field from marshmallow for custom field definition

app = Flask(__name__)

# --- MongoDB Configuration ---
# REPLACE THIS WITH YOUR ACTUAL MONGODB ATLAS CONNECTION STRING
# Example: MONGO_URI = "mongodb+srv://myuser:mypassword@cluster0.abcde.mongodb.net/?retryWrites=true&w=majority"
MONGO_URI = ""
DATABASE_NAME = "sample_mflix" # You can change the database name
COLLECTION_NAME = "movies"

try:
    client = MongoClient(MONGO_URI)
    db = client[DATABASE_NAME]
    movies_collection = db[COLLECTION_NAME]
    # Optional: Command to check if connection is successful
    client.admin.command('ping')
    print("Successfully connected to MongoDB Atlas!")
except Exception as e:
    print(f"Error connecting to MongoDB Atlas: {e}")
    # Depending on your deployment strategy, you might want to exit or handle this differently
    # For a simple script, printing and continuing might be okay, but in production,
    # you'd likely want to crash early if the DB connection is essential.
    # raise e # Uncomment this line if you want the app to fail if DB connection fails

# --- Custom Marshmallow Fields to Handle Empty Strings ---
class FloatAllowEmpty(fields.Float):
    """Custom Float field that treats empty strings as None during serialization."""
    def _serialize(self, value, attr, obj, **kwargs):
        if value == '':
            return None # Treat empty string as None
        return super()._serialize(value, attr, obj, **kwargs)

class IntegerAllowEmpty(fields.Int):
    """Custom Integer field that treats empty strings as None during serialization."""
    def _serialize(self, value, attr, obj, **kwargs):
        if value == '':
            return None # Treat empty string as None
        return super()._serialize(value, attr, obj, **kwargs)


# --- Marshmallow Schemas (Update Integer Fields) ---

# Schema for the 'awards' nested object - USE THE CUSTOM FIELD HERE
class AwardSchema(Schema):
    # Use IntegerAllowEmpty instead of fields.Int
    wins = IntegerAllowEmpty(allow_none=True)
    nominations = IntegerAllowEmpty(allow_none=True)
    text = fields.Str(allow_none=True)

# Schema for the 'imdb' nested object - USE THE CUSTOM FIELD HERE
class ImdbSchema(Schema):
    rating = FloatAllowEmpty(allow_none=True)
    # Use IntegerAllowEmpty instead of fields.Int
    votes = IntegerAllowEmpty(allow_none=True)
    id = IntegerAllowEmpty(allow_none=True) # IMDb's internal ID

# Schemas for the 'tomatoes' nested object - USE THE CUSTOM FIELD HERE
class TomatoViewerSchema(Schema):
    rating = FloatAllowEmpty(allow_none=True)
    # Use IntegerAllowEmpty instead of fields.Int
    numReviews = IntegerAllowEmpty(allow_none=True)
    meter = IntegerAllowEmpty(allow_none=True)

class TomatoCriticSchema(Schema):
    rating = FloatAllowEmpty(allow_none=True)
    # Use IntegerAllowEmpty instead of fields.Int
    numReviews = IntegerAllowEmpty(allow_none=True)
    meter = IntegerAllowEmpty(allow_none=True)

class TomatoSchema(Schema):
    viewer = fields.Nested(TomatoViewerSchema, allow_none=True)
    critic = fields.Nested(TomatoCriticSchema, allow_none=True)
    # Use IntegerAllowEmpty instead of fields.Int
    fresh = IntegerAllowEmpty(allow_none=True)
    rotten = IntegerAllowEmpty(allow_none=True)
    lastUpdated = fields.DateTime(allow_none=True)


# Main Movie Schema covering all fields - USE THE CUSTOM FIELD HERE
class MovieSchema(Schema):
    id = fields.Str(dump_only=True, attribute="_id")

    plot = fields.Str(allow_none=True)
    genres = fields.List(fields.Str(), allow_none=True)
    # Use IntegerAllowEmpty instead of fields.Int
    runtime = IntegerAllowEmpty(allow_none=True)
    cast = fields.List(fields.Str(), allow_none=True)
    poster = fields.Str(allow_none=True)
    title = fields.Str(required=True, error_messages={"required": "Title is required."})
    fullplot = fields.Str(allow_none=True)
    languages = fields.List(fields.Str(), allow_none=True)
    released = fields.DateTime(allow_none=True) # Keep as DateTime if stored as BSON Date
    directors = fields.List(fields.Str(), allow_none=True)
    rated = fields.Str(allow_none=True)
    awards = fields.Nested(AwardSchema, allow_none=True)

    # Assuming this is stored as a string
    lastupdated = fields.Str(allow_none=True)

    # Year is required for POST/PUT, but might be '' in old data. Use custom field.
    year = IntegerAllowEmpty(
        required=True, # Keep required for validation on POST/PUT
        validate=lambda x: isinstance(x, int) and x > 0, # Validation applies *after* deserialization
        error_messages={"required": "Year is required.", "validator_failed": "Year must be a positive integer."}
    )

    imdb = fields.Nested(ImdbSchema, allow_none=True)
    countries = fields.List(fields.Str(), allow_none=True)
    type = fields.Str(allow_none=True)
    tomatoes = fields.Nested(TomatoSchema, allow_none=True)

    # Use IntegerAllowEmpty instead of fields.Int
    num_mflix_comments = IntegerAllowEmpty(allow_none=True)


    class Meta:
        unknown = INCLUDE # or EXCLUDE

# Instantiate schemas
movie_schema = MovieSchema()
movies_schema = MovieSchema(many=True)
# --- (rest of your Flask routes and code) ---

# --- Helper function to load data using schema and handle validation errors ---
def load_data_and_validate(schema, data, partial=False):
    """Helper to load data using a schema and return data or validation errors."""
    try:
        # load() performs deserialization and validation
        # partial=True allows partial updates (missing required fields are ignored if not present)
        validated_data = schema.load(data, partial=partial)
        return validated_data, None # Return data and no error
    except ValidationError as err:
        return None, err.messages # Return no data and error messages


# --- Routes ---

@app.route('/')
def home():
    """Basic home route."""
    return "Welcome to the Advanced Movie API with Full Schema!"

@app.route('/movies', methods=['POST'])
def add_movie():
    """Adds a new movie with validation using the comprehensive schema."""
    movie_data = request.json
    if not movie_data:
        return jsonify({"error": "No input data provided"}), 400

    # Validate incoming data using the schema. partial=False means all required fields must be present.
    validated_data, errors = load_data_and_validate(movie_schema, movie_data, partial=False)

    if errors:
        return jsonify({"errors": errors}), 400 # Return validation errors with 400

    try:
        # MongoDB automatically adds _id if not provided
        result = movies_collection.insert_one(validated_data)
        new_movie_id = result.inserted_id

        # Fetch the newly inserted movie to return in the response
        new_movie = movies_collection.find_one({"_id": new_movie_id})

        # movie_schema.dump() serializes the document for the JSON response
        # It handles converting ObjectId to string 'id' and datetime objects
        return jsonify({
            "message": "Movie added successfully",
            "movie": movie_schema.dump(new_movie)
        }), 201 # 201 Created

    except Exception as e:
        print(f"Database error during movie insertion: {e}")
        return jsonify({"error": "Internal server error during database operation"}), 500 # 500 Internal Server Error

# Helper to convert ObjectId to string
def serialize_movie(movie):
    movie["_id"] = str(movie["_id"])
    return movie

@app.route("/movies", methods=["GET"])
def get_movies_paginated():
    # Get pagination parameters
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    skip = (page - 1) * per_page

    # Query with pagination
    cursor = movies_collection.find().skip(skip).limit(per_page)
    movies = [serialize_movie(movie) for movie in cursor]

    # Optional: get total count
    total_count = movies_collection.count_documents({})

    return jsonify({
        "page": page,
        "per_page": per_page,
        "total": total_count,
        "movies": movies
    })
@app.route('/movies/<id>', methods=['GET'])
def get_movie(id):
    """Retrieves a single movie by ID using the comprehensive schema for serialization."""
    try:
        # Convert string ID from URL to MongoDB ObjectId
        movie_id = ObjectId(id)
    except InvalidId:
        # Return 400 if the ID format is invalid
        return jsonify({"error": "Invalid movie ID format"}), 400

    try:
        # Find a single document by its ObjectId
        movie = movies_collection.find_one({"_id": movie_id})

        if movie:
            # Use the schema to dump (serialize) the single movie
            # .dump() handles ObjectId to string and date/time conversion
            return jsonify(movie_schema.dump(movie)), 200
        else:
            # Return 404 if no movie is found with that ID
            return jsonify({"error": "Movie not found"}), 404

    except Exception as e:
        print(f"Database error during fetching single movie: {e}")
        return jsonify({"error": "Internal server error during database operation"}), 500


@app.route('/movies/<id>', methods=['PUT'])
def update_movie(id):
    """Updates a movie by ID with validation using the comprehensive schema."""
    try:
        # Convert string ID from URL to MongoDB ObjectId
        movie_id = ObjectId(id)
    except InvalidId:
        return jsonify({"error": "Invalid movie ID format"}), 400

    update_data = request.json
    if not update_data:
        return jsonify({"error": "No update data provided"}), 400

    # Validate incoming data using the schema. partial=True allows updating only a subset of fields.
    validated_data, errors = load_data_and_validate(movie_schema, update_data, partial=True)

    if errors:
        return jsonify({"errors": errors}), 400 # Return validation errors with 400

    # Remove the 'id' field from validated_data if it exists, as we don't update the MongoDB _id
    validated_data.pop('id', None)

    # If validated_data is empty after validation, there's nothing valid to update
    if not validated_data:
         return jsonify({"error": "No valid fields provided for update"}), 400

    try:
        # Update the document using $set
        result = movies_collection.update_one(
            {"_id": movie_id},
            {"$set": validated_data}
        )

        if result.matched_count == 0:
            # Return 404 if movie not found
            return jsonify({"error": "Movie not found"}), 404
        # Note: modified_count might be 0 if the data sent is identical to the existing data
        # In that case, matched_count will be 1 but modified_count will be 0.
        # We return 200 as the request was processed successfully even if no change occurred.

        # Fetch and return the updated movie
        updated_movie = movies_collection.find_one({"_id": movie_id})
        # Use the schema to dump (serialize) the updated movie
        return jsonify({
            "message": "Movie updated successfully",
            "movie": movie_schema.dump(updated_movie)
        }), 200 # 200 OK

    except Exception as e:
        print(f"Database error during movie update: {e}")
        return jsonify({"error": "Internal server error during database operation"}), 500


@app.route('/movies/<id>', methods=['DELETE'])
def delete_movie(id):
    """Deletes a movie by ID."""
    try:
        # Convert string ID from URL to MongoDB ObjectId
        movie_id = ObjectId(id)
    except InvalidId:
        return jsonify({"error": "Invalid movie ID format"}), 400

    try:
        # Delete the document
        result = movies_collection.delete_one({"_id": movie_id})

        if result.deleted_count == 1:
            # Return success message if one document was deleted
            return jsonify({"message": "Movie deleted successfully"}), 200
        else:
            # Return 404 if not found
            return jsonify({"error": "Movie not found"}), 404

    except Exception as e:
        print(f"Database error during movie deletion: {e}")
        return jsonify({"error": "Internal server error during database operation"}), 500

# --- Run the app ---
if __name__ == '__main__':
    # Make sure you replace YOUR_MONGODB_ATLAS_CONNECTION_STRING above
    if MONGO_URI == "":
        print("\n!!! IMPORTANT: Please replace 'YOUR_MONGODB_ATLAS_CONNECTION_STRING' in app.py with your actual MongoDB Atlas URI. !!!\n")
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 3000)))