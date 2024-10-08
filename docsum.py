import os
import argparse
import re
import time
import fulltext
import groq
from bs4 import BeautifulSoup
import chardet

# Detect the encoding of the file and extract text from different formats
def detect_encoding_and_extract_text(filepath):
    with open(filepath, 'rb') as f:
        encoding_info = chardet.detect(f.read())
        detected_encoding = encoding_info['encoding']

    if filepath.endswith('.html'):
        with open(filepath, 'r', encoding=detected_encoding) as f:
            soup = BeautifulSoup(f, 'html.parser')
            return soup.get_text()
    else:
        try:
            with open(filepath, 'r', encoding=detected_encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            return fulltext.get(filepath)

# Chunk the document into manageable sizes for processing
def chunk_text_by_size(text, max_chunk_size=4000):
    if not text:
        return []

    # Split the document by paragraphs (two or more newlines)
    paragraphs = re.split(r'\n{2,}', text)
    paragraphs = [para.strip() for para in paragraphs if para.strip()]  # Clean paragraphs

    chunks = []
    current_chunk = []

    # Assemble chunks from paragraphs
    for para in paragraphs:
        # Check if adding this paragraph exceeds the chunk size
        if sum(len(p) for p in current_chunk) + len(para) + len(current_chunk) * 2 > max_chunk_size:
            chunks.append("\n\n".join(current_chunk).strip())
            current_chunk = [para]
        else:
            current_chunk.append(para)

    # Add any remaining paragraphs to the final chunk
    if current_chunk:
        chunks.append("\n\n".join(current_chunk).strip())

    return chunks

# Perform Groq API queries with retry logic
def perform_groq_query(text_chunk, api_client, retry_delay=5):
    try:
        return api_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "Summarize the input text below in one paragraph at a 5th-grade reading level."},
                {"role": "user", "content": text_chunk},
            ],
            model="llama3-8b-8192",
        )
    except groq.InternalServerError:
        time.sleep(retry_delay)
        return perform_groq_query(text_chunk, api_client)
    except (groq.RateLimitError, groq.BadRequestError) as e:
        if 'RMP' in str(e):
            time.sleep(retry_delay)
            return perform_groq_query(text_chunk, api_client)
        else:
            chunked_text = chunk_text_by_size(text_chunk)
            summarized_chunks = [perform_groq_query(chunk, api_client).choices[0].message.content for chunk in chunked_text]
            combined_summary = " ".join(summarized_chunks)
            return perform_groq_query(combined_summary, api_client)

# Main function to process the document and generate the summary
def summarize_document(filepath, api_key):
    api_client = groq.Groq(api_key=api_key)
    document_text = detect_encoding_and_extract_text(filepath)
    summary_response = perform_groq_query(document_text, api_client)
    return summary_response.choices[0].message.content

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Summarize a document using the Groq API.")
    parser.add_argument('filename', help="Path to the document to summarize.")
    args = parser.parse_args()

    api_key = os.getenv("GROQ_API_KEY")
    final_summary = summarize_document(args.filename, api_key)
    print(final_summary)

