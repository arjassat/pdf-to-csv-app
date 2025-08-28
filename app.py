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
import re # We'll use regular expressions for text cleaning

# --- Main App Configuration ---
# Set the title and a brief description for your app.
st.set_page_config(page_title="PDF to CSV Bank Converter", layout="centered")

# --- Function to parse ABSA PDFs using a rule-based approach ---
def parse_absa_pdf(pdf_text):
    """
    Parses transactions from ABSA PDFs using regular expressions.
    This approach is more robust for inconsistent formats.
    """
    st.info("Using rule-based parser for ABSA file.")
    transactions = []
    
    # Define a regex pattern to find transaction lines. This pattern looks for a date,
    # followed by a description, and then optional debit and credit amounts.
    # The pattern is complex to handle the inconsistent formatting.
    # Example: "29/04/2021 T 141.43 Ibank Payment To Settlement Absa Bank Simple Pay Payroll ,,,"
    # The text is flattened, so we look for dates followed by patterns of text and numbers.
    
    # This regex looks for a date, followed by text (description), and then two numbers,
    # which represent the debit and credit columns.
    # The ?P<name> syntax is used to create named capture groups for easier access.
    # The text is flattened and has many spaces, so we use '\s+' to match one or more spaces.
    pattern = re.compile(
        r'(\d{1,2}/\d{1,2}/\d{4})\s+'  # Date (e.g., 29/04/2021)
        r'(.+?)\s+'  # Description (non-greedy to stop before the next number)
        r'([\d\s,.]+\s+)?'  # Optional charge or extra text
        r'([\d\s,.-]+)\s*'  # Debit or Credit Amount (can have a '-' sign)
        r'(?P<credit>[\d\s,.]*)?' # Optional second number, usually the credit amount
        r'([\d\s,.]+\s*)?' # Optional charge
    )
    
    # Split the text into lines to process each transaction individually.
    lines = pdf_text.split("\n")
    
    for line in lines:
        if "statement no" in line.lower() or "transaction description" in line.lower() or "page" in line.lower():
            continue # Skip headers and other non-transaction lines

        # Remove extra spaces and make the line more manageable.
        line = re.sub(r'\s+', ' ', line).strip()
        
        match = pattern.search(line)
        if match:
            try:
                # Get the captured groups from the regex match.
                date_str = match.group(1).strip()
                description = match.group(2).strip()
                
                # Check for both debit and credit amounts to determine the sign.
                debit_str = match.group(4)
                credit_str = match.group('credit')
                
                amount = 0.0
                if credit_str and credit_str.strip() != "":
                    amount = float(credit_str.replace(" ", "").replace(",", ""))
                elif debit_str and debit_str.strip() != "":
                    # The debit amount will sometimes be preceded by a '-'.
                    amount = -abs(float(debit_str.replace(" ", "").replace(",", "").replace("-", "")))
                else:
                    continue # Skip transactions without a clear amount

                # Append the parsed transaction to the list.
                transactions.append({
                    "date": pd.to_datetime(date_str, format="%d/%m/%Y").strftime("%Y-%m-%d"),
                    "description": description,
                    "amount": amount
                })
            except (ValueError, IndexError):
                # If a line doesn't match the pattern or has a parsing error, skip it.
                continue

    st.success(f"Found {len(transactions)} transactions with rule-based parser.")
    return transactions

# --- Function to interact with the AI (for all other PDFs) ---
def process_with_ai(pdf_text):
    """
    Sends the extracted PDF text to the Gemini API to get structured transaction data.
    This is used for PDFs that have a more consistent structure.
    """
    st.info("Using AI-based parser.")
    prompt = f"""
    You are a bank statement transaction parser. Your task is to extract transactions
    from the following bank statement text. The bank can be FNB, Nedbank, Standard Bank,
    ABSA, or HBZ.
    ... [rest of the prompt as before]
    """
    
    # ... [rest of the API call logic as before]
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
    
    api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent"
    api_key = st.secrets["general"]["api_key"]

    try:
        response = requests.post(
            api_url,
            headers={'Content-Type': 'application/json'},
            params={'key': api_key},
            json=payload
        )
        response.raise_for_status()
        api_response_json = response.json()
        if api_response_json and api_response_json.get('candidates') and api_response_json['candidates'][0].get('content'):
            raw_text = api_response_json['candidates'][0]['content']['parts'][0]['text']
            transactions = json.loads(raw_text)
            st.success(f"Found {len(transactions)} transactions with AI parser.")
            return transactions
        else:
            st.error("AI processing failed. Please try a different PDF or contact support.")
            st.json(api_response_json)
            return []
    except (requests.exceptions.RequestException, json.JSONDecodeError, Exception) as e:
        st.error(f"An error occurred during AI processing: {e}")
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

    # File uploader widget to let the user upload multiple PDFs.
    uploaded_files = st.file_uploader(
        "Upload your PDF bank statements:",
        type="pdf",
        accept_multiple_files=True,
        key="pdf_uploader"
    )

    # Check if files have been uploaded by the user.
    if uploaded_files:
        if st.button("Convert All to CSV"):
            with st.spinner("🚀 Processing files and extracting transactions... This may take a moment."):
                all_transactions = []
                # Loop through each uploaded file.
                for uploaded_file in uploaded_files:
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
                        
                        st.info(f"Processing transactions from: {uploaded_file.name}")
                        
                        # Conditional logic to use the correct parser.
                        if "absa" in uploaded_file.name.lower():
                            transactions = parse_absa_pdf(full_text)
                        else:
                            transactions = process_with_ai(full_text)
                            
                        all_transactions.extend(transactions)

                    except Exception as e:
                        st.error(f"Error reading PDF {uploaded_file.name}: {e}")
                
                # After processing all files, create a single DataFrame.
                if all_transactions:
                    df = pd.DataFrame(all_transactions, columns=['date', 'description', 'amount'])
                    
                    # Convert DataFrame to CSV.
                    csv_data = df.to_csv(index=False)
                    csv_bytes = csv_data.encode('utf-8')
                    
                    st.success("Conversion complete! 🎉")
                    st.dataframe(df) # Display the DataFrame for a quick preview.
                    
                    # Create a download button for the CSV file.
                    st.download_button(
                        label="Download Combined CSV",
                        data=csv_bytes,
                        file_name="bank_transactions.csv",
                        mime="text/csv"
                    )
                else:
                    st.warning("No transactions could be extracted from any of the uploaded PDFs.")

    # A simple message to guide the user if no file is uploaded yet.
    else:
        st.info("Please upload your PDF files to begin.")

# Run the main function when the script is executed.
if __name__ == "__main__":
    main()

