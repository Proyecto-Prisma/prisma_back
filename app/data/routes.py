from flask import Blueprint, request, jsonify, send_file, session, redirect, url_for
import pandas as pd
from io import BytesIO
import matplotlib.pyplot as plt

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

    scopus_file = request.files["scopus_file"]
    wos_file = request.files["wos_file"]

    # Check if filenames are provided
    if scopus_file.filename == "" or wos_file.filename == "":
        return jsonify({"error": "One of the files was not selected"}), 400

    # Reading the files into the appropriate DataFrames
    try:
        if scopus_file:  # Assuming Scopus files are CSVs
            data_store["scopus"] = pd.read_csv(scopus_file)  # type: ignore
        if wos_file:  # Assuming WoS files are Excel files
            data_store["wos"] = pd.read_excel(wos_file)  # type: ignore
    except Exception as e:
        app.logger.error(f"Failed to read file: {e}")  # type: ignore
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "Files uploaded successfully"}), 200


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
        app.logger.error(f"Error during processing: {e}")  # type: ignore
        return jsonify({"error": str(e)}), 500


@data_blueprint.route("/visualize/<chart_type>", methods=["GET"])
@cross_origin()
def visualize_data(chart_type):
    if data_store["processed"] is None:
        return jsonify({"error": "Data has not been processed"}), 400

    if chart_type not in ["keywords", "countries", "cited_times"]:
        return jsonify({"error": f"Invalid chart type: {chart_type}"}), 400

    # Get the processed data
    processed_data = data_store["processed"]

    if chart_type == "keywords":
    # Check if processed_data["Author Keywords"] is a pandas Series
        if isinstance(processed_data["Author Keywords"], pd.Series):
            # Count the frequency of each keyword
            keyword_counts = processed_data["Author Keywords"].str.split(";").explode().value_counts()

            # Convert the counts to a list of dictionaries
            keyword_data = [{"keyword": keyword, "frequency": count} for keyword, count in keyword_counts.head(10).items()]
        else:
            # Handle the case where processed_data["Author Keywords"] is not a pandas Series
            return jsonify({"error": "Author Keywords data is not valid"}), 400

    elif chart_type == "countries":
        # Count the frequency of each country
        country_counts = processed_data["Affiliations"].value_counts()

        # Convert the counts to a list of dictionaries
        country_data = [{"country": country, "frequency": count} for country, count in country_counts.head(10).items()]

    elif chart_type == "cited_times":
        # Count the frequency of cited times
        cited_times_counts = processed_data["Times Cited"].value_counts()

        # Convert the counts to a list of dictionaries
        cited_times_data = [{"cited_times": times, "frequency": count} for times, count in cited_times_counts.items()]

    if chart_type == "keywords":
        return jsonify({"chart_data": keyword_data})
    elif chart_type == "countries":
        return jsonify({"chart_data": country_data})
    elif chart_type == "cited_times":
        return jsonify({"chart_data": cited_times_data})



@data_blueprint.route("/export", methods=["GET"])
@cross_origin()
def export_data():
    if data_store["processed"] is None:
        return jsonify({"error": "Data has not been processed"}), 400

    # Convert processed DataFrame to Excel
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:  # type: ignore
        data_store["processed"].to_excel(writer, index=False)
    output.seek(0)
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="processed_data.xlsx",
    )



