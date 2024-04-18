import json
from typing import Counter
from flask import Blueprint, request, jsonify, send_file, session, redirect, url_for
import pandas as pd
from io import BytesIO
import matplotlib.pyplot as plt
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.probability import FreqDist
from wordcloud import WordCloud
import re
from collections import Counter
nltk.download('stopwords')
from firebase_admin import db, storage
from datetime import datetime

import app
from .utils import data_store
from flask_cors import CORS, cross_origin  # type: ignore


data_blueprint = Blueprint("data", __name__)


@data_blueprint.route("/upload", methods=["POST"])
@cross_origin()
def upload_file():
    print(request.files)

    # Check if both files are provided
    if "scopus_file" not in request.files or "wos_file" not in request.files:
        return jsonify({"error": "Missing Scopus or WoS file parameter"}), 400

    user_uid = request.form.get('user_uid', None)
    scopus_file = request.files["scopus_file"]
    wos_file = request.files["wos_file"]

    cadena_busqueda = request.form.get('cadena_busqueda', "")

    if not user_uid or not scopus_file or not wos_file:
        return jsonify({"error": "Missing files or user UID"}), 400

    # Check if filenames are provided
    if scopus_file.filename == "" or wos_file.filename == "":
        return jsonify({"error": "One of the files was not selected"}), 400

    # Reading the files into the appropriate DataFrames
    try:
        user_data = {
            "user": user_uid,
            "files": {},
            "cadena_busqueda": cadena_busqueda,
            "creacion_registro": datetime.now().isoformat()  # ISO formatted current date and time
        }

        bucket = storage.bucket()

        if scopus_file:  # Assuming Scopus files are CSVs
            scopus_df = pd.read_csv(scopus_file)
            data_store["scopus"] = scopus_df
            scopus_file.seek(0)

            # Upload Scopus file to Firebase Storage
            scopus_blob = bucket.blob(f'scopus_files/{user_data["user"]}/{user_data["creacion_registro"]}/{scopus_file.filename}')
            scopus_blob.upload_from_file(scopus_file, content_type=scopus_file.content_type)
            scopus_blob.make_public()
            user_data["files"]["scopus_file"] = scopus_blob.public_url

        if wos_file:  # Assuming WoS files are Excel files
            wos_df = pd.read_excel(wos_file)
            data_store["wos"] = wos_df
            wos_file.seek(0)

            # Upload WoS file to Firebase Storage
            wos_blob = bucket.blob(f'wos_files/{user_data["user"]}/{user_data["creacion_registro"]}/{wos_file.filename}')
            wos_blob.upload_from_file(wos_file, content_type=wos_file.content_type)
            wos_blob.make_public()
            user_data["files"]["wos_file"] = wos_blob.public_url

        # Firebase
        ref = db.reference('/uploads')
        new_ref = ref.push(user_data)
        upload_key = new_ref.key

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "message": "Files uploaded successfully",
        "upload_key": upload_key
    }), 200


def get_country_wos(address):
    # Split the address string and return the country part
    # This is just an example, adapt it to your specific address format
    country = address.split("]")[-1].split(";")[-1].strip()
    return country


@data_blueprint.route("/process", methods=["GET"])
@cross_origin()
def process_data():
    # Check if data has been uploaded
    if data_store["scopus"] is None or data_store["wos"] is None:
        return (
            jsonify(
                {"error": "Scopus and WoS data must be uploaded before processing"}
            ),
            400,
        )

    # Check if any of the data frames are empty
    if data_store["scopus"].empty or data_store["wos"].empty:
        return jsonify({"error": "One of the data sources is empty"}), 400

    try:
        # Start processing for Scopus data
        df_scopus = data_store["scopus"]
        df_scopus["Times Cited"] = df_scopus["Cited by"].apply(
            lambda x: int(x) if pd.notnull(x) else "No data"
        )
        df_scopus["Affiliations"] = df_scopus["Affiliations"].apply(
            lambda x: x.split(",")[-1].strip() if pd.notnull(x) else "No data"
        )
        df_scopus = df_scopus[
            [
                "Authors",
                "Title",
                "Year",
                "Affiliations",
                "Times Cited",
                "DOI",
                "Source title",
                "Abstract",
                "Author Keywords",
                "Document Type",
                "Source",
            ]
        ]
        df_scopus.rename(
            columns={
                "Title": "Article Title",
                "Year": "Publication Year",
                "Source title": "Source Title",
            },
            inplace=True,
        )

        # Start processing for WoS data
        df_wos = data_store["wos"]
        df_wos["Affiliations"] = df_wos["Addresses"].apply(lambda x: get_country_wos(x))
        df_wos = df_wos[
            [
                "Authors",
                "Article Title",
                "Publication Year",
                "Affiliations",
                "Cited Reference Count",
                "DOI",
                "Source Title",
                "Abstract",
                "Author Keywords",
                "Document Type",
            ]
        ]
        df_wos.rename(columns={"Cited Reference Count": "Times Cited"}, inplace=True)
        df_wos["Source"] = "WoS"

        # Merging Scopus and WoS data
        combined_data = pd.concat([df_scopus, df_wos], ignore_index=True)
        combined_data.reset_index(inplace=True, drop=True)

        # Additional processing steps can go here...
        # For example, removing duplicates based on DOI, Article Title, and Abstract.
        combined_data.drop_duplicates(subset="DOI", inplace=True, ignore_index=True)
        combined_data.drop_duplicates(
            subset="Article Title", inplace=True, ignore_index=True
        )
        combined_data.drop_duplicates(
            subset="Abstract", inplace=True, ignore_index=True
        )

        # Perform ranking based on a predefined 'get_q' function
        # Assuming 'get_q' function and 'scimagojr_2020.csv' file are available and correctly implemented in your Flask app
        # df_q = pd.read_csv('/path/to/scimagojr_2020.csv', sep=';')
        # combined_data["Cuartil"] = combined_data["Source Title"].apply(lambda x: get_q(x, df_q))

        # Store the processed data
        data_store["processed"] = combined_data  # type: ignore

        return (
            jsonify(
                {
                    "message": "Data processed successfully",
                    "processed_rows": combined_data.shape[0],
                }
            ),
            200,
        )

    except Exception as e:
        # If any error occurs during processing, catch it and return as internal server error
        return jsonify({"error": str(e)}), 500


@data_blueprint.route("/visualize/<chart_type>", methods=["GET"])
@cross_origin()
def visualize_data(chart_type):
    if data_store["processed"] is None:
        return jsonify({"error": "Data has not been processed"}), 400

    if chart_type not in ["keywords", "countries", "cited_times", "authors", "publication_years", "abstract", "institution", "most_frequent_keywords", "cites", "authors_geographic_distribution"]:
        return jsonify({"error": f"Invalid chart type: {chart_type}"}), 400

    # Get the processed data
    processed_data = data_store["processed"]

    if chart_type == "keywords":
        # Count the frequency of each keyword
        keyword_counts = processed_data["Author Keywords"].str.split(";").explode().value_counts()

        # Convert the counts to a list of dictionaries
        keyword_data = [{"keyword": keyword, "frequency": count} for keyword, count in keyword_counts.head(10).items()]

        return jsonify({"chart_data": keyword_data})

    elif chart_type == "countries":
        # Count the frequency of each country
        country_counts = processed_data["Affiliations"].value_counts()

        # Convert the counts to a list of dictionaries
        country_data = [{"country": country, "frequency": count} for country, count in country_counts.head(10).items()]

        return jsonify({"chart_data": country_data})

    elif chart_type == "cited_times":
        # Create a dictionary to store cited times counts for each article title
        cited_times_data = {}

        # Iterate over each row in the processed data
        for index, row in processed_data.iterrows():
            # Extract article title and cited times
            title = row["Article Title"]
            cited_times = row["Times Cited"]

            # Check if the article title is already in the dictionary
            if title in cited_times_data:
                # Increment the count for the cited times
                cited_times_data[title] += cited_times
            else:
                # Add the article title to the dictionary
                cited_times_data[title] = cited_times

        # Convert the dictionary to a list of dictionaries
        cited_times_list = [{"title": title, "cited_times": times} for title, times in cited_times_data.items()]

        return jsonify({"chart_data": cited_times_list})

    elif chart_type == "authors":
        # Count the frequency of each author
        author_counts = processed_data["Authors"].str.split(";").explode().value_counts()

        # Convert the counts to a list of dictionaries
        author_data = [{"author": author, "frequency": count} for author, count in author_counts.head(10).items()]

        return jsonify({"chart_data": author_data})

    elif chart_type == "publication_years":
        # Extract publication years
        publication_years = processed_data["Publication Year"]

        # Count the frequency of each publication year
        year_counts = publication_years.value_counts().sort_index()

        # Convert the counts to a list of dictionaries
        year_data = [{"year": year, "frequency": count} for year, count in year_counts.items()]

        return jsonify({"chart_data": year_data})

    elif chart_type == "abstract":
        # Extraer texto del abstract
        abstract_text = processed_data["Abstract"].str.cat(sep=" ")

        # Tokenizar el texto (dividir en palabras)
        words = re.findall(r'\b\w+\b', abstract_text.lower())

        # Filtrar palabras vacías
        stop_words = set(stopwords.words('english'))
        words = [word for word in words if word not in stop_words]

        # Contar la frecuencia de cada palabra
        word_counts = Counter(words)

        # Obtener las 10 primeras palabras que más se repiten
        most_common_words = word_counts.most_common(10)

        # Extraer las palabras y sus frecuencias
        top_10_words = [{"text": word, "value": count} for word, count in most_common_words]

        return jsonify({"chart_data": top_10_words})

    elif chart_type == "authors_countries":
        # Count the frequency of each country mentioned in the affiliations column
        country_counts = processed_data["Affiliations"].str.extract(r'\b(\w+)\b').stack().value_counts()

        # Convert the counts to a list of dictionaries
        country_data = [{"country": country, "frequency": count} for country, count in country_counts.items()]

        return jsonify({"chart_data": country_data})



    # You can implement the other chart types similarly
    else:
        return jsonify({"error": "Chart type not implemented yet"}), 400







@data_blueprint.route("/export", methods=["POST"])
@cross_origin()
def export_data():
    if data_store["processed"] is None:
        return jsonify({"error": "Data has not been processed"}), 400

    folder_id = request.form.get('folder_id')
    if not folder_id:
        return jsonify({"error": "Folder ID is required"}), 400

    # Convert processed DataFrame to Excel
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:  # type: ignore
        data_store["processed"].to_excel(writer, index=False)
    output.seek(0)

    bucket = storage.bucket()
    blob = bucket.blob(f'uploads/{folder_id}/files/processed_data.xlsx')

    blob.upload_from_string(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    url = blob.public_url

    # Update the reference in the Realtime Database
    ref = db.reference('uploads')
    ref.update({
        'processed_data': url
    })

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="processed_data.xlsx",
    )
