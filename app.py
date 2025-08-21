# app.py

# Import necessary libraries. We'll use Streamlit for the app interface,
# pandas to create the CSV, and PyMuPDF to read the PDF.
import streamlit as st
import pandas as pd
import fitz  # This is the PyMuPDF library
import json
import base64
import io
import requests # We will use the standard requests library for API calls
import os # Import the os module to use environment variables

# --- Main App Configuration ---
# Set the title and a brief description for your app.
st.set_page_config(page_title="PDF to CSV Bank Converter", layout="centered")

# --- Function to interact with the AI ---
def process_with_ai(pdf_text):
    """
    Sends the extracted PDF text to the Gemini API to get structured transaction data.
    We are using gemini-2.5-flash-preview-05-20, which is a powerful model
    for this type of structured data extraction.
    """
    # The prompt is a set of instructions for the AI.
    # It tells the AI exactly what to look for and how to format the output.
    prompt = f"""
    You are a bank statement transaction parser. Your task is to extract transactions
    from the following bank statement text. The bank can be FNB, Nedbank, Standard Bank,
    ABSA, or HBZ.

    For each transaction, extract the date, description, and amount.
    Format the output as a JSON array of objects.
    The amount must be a number: positive for credits (CR/deposit) and negative for debits (DR/withdrawal).
    The output should only be the JSON, with no other text or explanation.

    Fields to extract for each transaction object:
    - 'date': The transaction date in 'YYYY-MM-DD' format.
    - 'description': A concise description of the transaction.
    - 'amount': The transaction amount as a number (e.g., 100.50 or -50.00).

    If a transaction does not have a clear date, description, and amount, you must ignore it.

    Bank Statement Text:
    {pdf_text}
    """

    # --- API Call to Gemini ---
    # This is where the AI processing happens. We configure it to return JSON directly.
    # The schema is now updated to only include date, description, and amount.
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string"},
                        "description": {"type": "string"},
                        "amount": {"type": "number"}
                    },
                    "required": ["date", "description", "amount"]
                }
            }
        }
    }

    # This URL is the entry point for the AI model.
    api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent"
    
    # We retrieve the API key securely from Streamlit's secrets.
    # The key is named 'api_key' under the 'general' section in the secrets.toml file.
    api_key = st.secrets["general"]["api_key"]

    try:
        # We'll now use the standard requests library which works reliably with Streamlit.
        response = requests.post(
            api_url,
            headers={'Content-Type': 'application/json'},
            params={'key': api_key},
            json=payload
        )
        response.raise_for_status() # Raise an exception for bad status codes
        
        # Check if the API response is valid and contains content.
        api_response_json = response.json()
        if api_response_json and api_response_json.get('candidates') and api_response_json['candidates'][0].get('content'):
            raw_text = api_response_json['candidates'][0]['content']['parts'][0]['text']
            # Parse the JSON string into a Python list of dictionaries.
            transactions = json.loads(raw_text)
            return transactions
        else:
            st.error("AI processing failed. Please try a different PDF or contact support.")
            st.json(api_response_json) # Displaying the raw response can help with debugging
            return []
    except requests.exceptions.HTTPError as errh:
        st.error(f"HTTP Error: {errh}")
        return []
    except requests.exceptions.RequestException as err:
        st.error(f"An error occurred during API call: {err}")
        return []
    except json.JSONDecodeError as err:
        st.error(f"Failed to decode JSON response from AI: {err}")
        return []
    except Exception as e:
        st.error(f"An unexpected error occurred during AI processing: {e}")
        return []

# --- Main App UI Layout ---
def main():
    """
    This function contains the main user interface and logic for the Streamlit app.
    """
    st.title("📄 PDF to CSV Transaction Converter")
    st.markdown("""
    **Simply upload your bank statement PDF and let the AI extract your transactions to a clean CSV file.**

    Supported Banks: FNB, Nedbank, Standard Bank, ABSA, and HBZ.
    """)

    # File uploader widget to let the user upload a PDF.
    uploaded_file = st.file_uploader(
        "Upload a PDF bank statement:",
        type="pdf",
        accept_multiple_files=False,
        key="pdf_uploader"
    )

    # Check if a file has been uploaded by the user.
    if uploaded_file:
        # Show a spinner to indicate that the app is working.
        with st.spinner("Processing PDF and extracting text..."):
            try:
                # Read the uploaded PDF file's content in memory.
                pdf_bytes = uploaded_file.getvalue()
                pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
                
                # Extract all text from the PDF.
                full_text = ""
                for page_num in range(len(pdf_document)):
                    page = pdf_document.load_page(page_num)
                    full_text += page.get_text()
                
                pdf_document.close()
                st.success("PDF text extracted successfully!")

            except Exception as e:
                st.error(f"Error reading PDF: {e}")
                return # Stop execution if PDF reading fails.

        # Use a button to start the AI processing.
        if st.button("Convert to CSV"):
            with st.spinner("🚀 Sending to AI for transaction extraction... This may take a moment."):
                # Call the AI processing function.
                transactions = process_with_ai(full_text)

                if transactions:
                    # Convert the list of dictionaries to a pandas DataFrame.
                    # We explicitly set the columns here to ensure the order is correct.
                    df = pd.DataFrame(transactions, columns=['date', 'description', 'amount'])
                    
                    # Convert DataFrame to CSV.
                    csv_data = df.to_csv(index=False)
                    csv_bytes = csv_data.encode('utf-8')
                    
                    st.success("Conversion complete! 🎉")
                    st.dataframe(df) # Display the DataFrame for a quick preview.
                    
                    # Create a download button for the CSV file.
                    st.download_button(
                        label="Download CSV",
                        data=csv_bytes,
                        file_name="bank_transactions.csv",
                        mime="text/csv"
                    )
                else:
                    st.warning("No transactions could be extracted from the PDF.")

    # A simple message to guide the user if no file is uploaded yet.
    else:
        st.info("Please upload a PDF file to begin.")

# Run the main function when the script is executed.
if __name__ == "__main__":
    main()
