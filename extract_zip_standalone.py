import os
import re
import zipfile
import tarfile
import io
import py7zr
import chardet

# Configuration - set default paths that can be overridden with environment variables
default_results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
default_logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

results_dir = os.environ.get("results.csv", default_results_dir)
base_folder = os.environ.get("logs", default_logs_dir)

# Global variables for tracking
processed_csv_names = []
missing_date_archives = []
error_files = set()
global_raw_lines = 0
global_filtered_lines = 0

def extract_date(file_path):
    m = re.search(r'\d{4}[-_]\d{2}[-_]\d{2}', file_path)
    if m:
        date_str = m.group(0)
        return date_str.replace('_', '-')  # convert underscores to hyphens
    else:
        return "0000-00-00"

def append_date_to_lines(lines, date):
    return [line.rstrip("\n") + "," + date + "\n" for line in lines]

def read_csv_lines(source):
    data = source.read()
    detected = chardet.detect(data)
    encoding = detected.get('encoding')
    if encoding is None:
        encoding = 'utf-8-sig'  # fallback encoding if detection fails
    return io.StringIO(data.decode(encoding, errors='replace')).readlines()

def check_nonprintable(lines):
    for idx, line in enumerate(lines, start=1):
        if any((ord(ch) < 32 and ch not in "\n\r\t") for ch in line):
            print(f"Warning: Non-printable character found in line {idx}: {line.strip()}")

def add_date_column(csv_file):
    date = extract_date(csv_file)
    with open(csv_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    updated_lines = []
    for line in lines:
        columns = line.rstrip("\n").split(',')
        if len(columns) < 8:
            columns.extend([''] * (8 - len(columns)))
        columns.insert(8, date)
        updated_lines.append(','.join(columns) + "\n")
    with open(csv_file, 'w', encoding='utf-8') as f:
        f.writelines(updated_lines)

def filter_nonprintable_lines(lines):
    filtered = []
    for idx, line in enumerate(lines, start=1):
        if len(line.strip().split(',')) <= 5:
            print(f"Warning: Excluded corrupted line with insufficient columns at {idx}: {line.strip()}")
            continue
        if "�" in line or any((ord(ch) < 32 and ch not in "\n\r\t") for ch in line):
            print(f"Warning: Excluded corrupted/non-printable line {idx}: {line.strip()}")
        else:
            filtered.append(line)
    return filtered

def merge_csv_from_zip(zip_path, merged_csv):
    global total_csv_found, processed_csv_names, missing_date_archives, error_files, global_raw_lines, global_filtered_lines
    csv_count = 0
    total_lines = 0
    date = extract_date(zip_path)
    if date == "0000-00-00":
        missing_date_archives.append(zip_path)
        print(f"Warning: Missing date in archive {zip_path}")
    with open(merged_csv, 'w', newline='', encoding='utf-8') as merged:
        with zipfile.ZipFile(zip_path, 'r') as z:
            for zipinfo in z.infolist():
                filename = zipinfo.filename
                if filename in error_files:
                    continue
                basename = os.path.basename(filename)
                if zipinfo.is_dir() or not (basename.lower().endswith('.csv') and len(basename) > 20):
                    continue
                csv_count += 1
                total_csv_found += 1
                processed_csv_names.append(zipinfo.filename)
                try:
                    with z.open(zipinfo) as source:
                        lines = read_csv_lines(source)
                        raw_count = len(lines)
                        filtered = filter_nonprintable_lines(lines)
                        filtered_count = len(filtered)
                        global_raw_lines += raw_count
                        global_filtered_lines += filtered_count
                        total_lines += filtered_count
                        merged.writelines(filtered)
                except Exception as e:
                    err_msg = f"Error processing file {filename} in {zip_path}: {e}"
                    print(err_msg)
                    error_files.add(filename)
                    with open(ERROR_LOG_FILE, "a", encoding="utf-8") as ef:
                        ef.write(err_msg + "\n")
    msg = (f"Merged CSV created at: {merged_csv}; Processed {csv_count} CSV files, total {total_lines} lines")
    with open(LOG_FILE, "a", encoding="utf-8") as lf:
        lf.write(msg + "\n")
    print(msg)
    return total_lines

def merge_csv_from_tar(tar_path, merged_csv):
    global total_csv_found, processed_csv_names, missing_date_archives, error_files, global_raw_lines, global_filtered_lines
    csv_count = 0
    total_lines = 0
    date = extract_date(tar_path)
    if date == "0000-00-00":
        missing_date_archives.append(tar_path)
        print(f"Warning: Missing date in archive {tar_path}")
    with open(merged_csv, 'w', newline='', encoding='utf-8') as merged:
        with tarfile.open(tar_path, 'r:*') as tar:
            for member in tar.getmembers():
                filename = member.name
                if filename in error_files:
                    continue
                basename = os.path.basename(filename)
                if not member.isfile() or not (basename.lower().endswith('.csv') and len(basename) > 20):
                    continue
                csv_count += 1
                total_csv_found += 1
                processed_csv_names.append(member.name)
                f = tar.extractfile(member)
                if f:
                    try:
                        lines = read_csv_lines(f)
                        raw_count = len(lines)
                        filtered = filter_nonprintable_lines(lines)
                        filtered_count = len(filtered)
                        global_raw_lines += raw_count
                        global_filtered_lines += filtered_count
                        total_lines += filtered_count
                        merged.writelines(filtered)
                    except Exception as e:
                        err_msg = f"Error processing file {filename} in {tar_path}: {e}"
                        print(err_msg)
                        error_files.add(filename)
                        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as ef:
                            ef.write(err_msg + "\n")
    msg = (f"Merged CSV created at: {merged_csv}; Processed {csv_count} CSV files, total {total_lines} lines")
    with open(LOG_FILE, "a", encoding="utf-8") as lf:
        lf.write(msg + "\n")
    print(msg)
    return total_lines

def merge_csv_from_7z(sevenz_path, merged_csv):
    global total_csv_found, processed_csv_names, missing_date_archives, error_files, global_raw_lines, global_filtered_lines
    csv_count = 0
    total_lines = 0
    date = extract_date(sevenz_path)
    if date == "0000-00-00":
        missing_date_archives.append(sevenz_path)
        print(f"Warning: Missing date in archive {sevenz_path}")
    with open(merged_csv, 'w', newline='', encoding='utf-8') as merged:
        with py7zr.SevenZipFile(sevenz_path, mode='r') as archive:
            all_files = archive.getnames()
            for member in all_files:
                if member in error_files:
                    continue
                basename = os.path.basename(os.path.normpath(member))
                if not (basename.lower().endswith('.csv') and len(basename) > 20):
                    continue
                try:
                    extracted = archive.read([member])
                except Exception as e:
                    err_msg = f"Error on file {member} in {sevenz_path}: {e}"
                    print(err_msg)
                    error_files.add(member)
                    with open(ERROR_LOG_FILE, "a", encoding="utf-8") as ef:
                        ef.write(err_msg + "\n")
                    continue
                if member in extracted:
                    csv_count += 1
                    total_csv_found += 1
                    processed_csv_names.append(member)
                    try:
                        lines = read_csv_lines(extracted[member])
                        raw_count = len(lines)
                        filtered = filter_nonprintable_lines(lines)
                        filtered_count = len(filtered)
                        global_raw_lines += raw_count
                        global_filtered_lines += filtered_count
                        total_lines += filtered_count
                        merged.writelines(filtered)
                    except Exception as e:
                        err_msg = f"Error processing file {member} in {sevenz_path}: {e}"
                        print(err_msg)
                        error_files.add(member)
                        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as ef:
                            ef.write(err_msg + "\n")
    msg = (f"Merged CSV created at: {merged_csv}; Processed {csv_count} CSV files, total {total_lines} lines")
    with open(LOG_FILE, "a", encoding="utf-8") as lf:
        lf.write(msg + "\n")
    print(msg)
    return total_lines

def merge_csv_from_compressed(file_path, merged_csv):
    if file_path.lower().endswith('.zip'):
        return merge_csv_from_zip(file_path, merged_csv)
    elif file_path.lower().endswith(('.tar', '.tar.gz', '.tgz')):
        return merge_csv_from_tar(file_path, merged_csv)
    elif file_path.lower().endswith('.7z'):
        return merge_csv_from_7z(file_path, merged_csv)
    else:
        msg = f"Unsupported compressed file: {file_path}"
        with open(LOG_FILE, "a", encoding="utf-8") as lf:
            lf.write(msg + "\n")
        print(msg)
        return 0

def verify_date_column(csv_file):
    expected_date = extract_date(csv_file)
    with open(csv_file, 'r', encoding='utf-8') as f:
        for line in f:
            columns = line.rstrip("\n").split(',')
            if len(columns) < 9 or columns[8] != expected_date:
                return False
    return True

def combine_all_csv_files(csv_files, output_path):
    """Combine multiple CSV files into a single CSV file (no headers)"""
    if not csv_files:
        print("No CSV files to combine")
        return 0
    
    # Create directories if needed
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    total_rows = 0
    
    with open(output_path, 'w', newline='', encoding='utf-8') as outfile:
        for file_path in csv_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as infile:
                    lines = infile.readlines()
                    
                    if not lines:
                        continue
                    
                    # Write all lines (no headers to skip)
                    for line in lines:
                        outfile.write(line)
                        total_rows += 1
                        
            except Exception as e:
                err_msg = f"Error combining file {file_path}: {e}"
                print(err_msg)
                with open(ERROR_LOG_FILE, "a", encoding="utf-8") as ef:
                    ef.write(err_msg + "\n")
    
    msg = f"Combined CSV created at: {output_path}; Total rows: {total_rows}"
    with open(LOG_FILE, "a", encoding="utf-8") as lf:
        lf.write(msg + "\n")
    print(msg)
    return total_rows

def update_column_based_on_index(combined_csv_path, index_csv_path):
    """
    Compare the 6th column of combined CSV with the 1st column of index file
    and replace with the 2nd column value from index file when there's a match
    """
    # Read index file and create lookup dictionary
    lookup = {}
    try:
        with open(index_csv_path, 'r', encoding='utf-8') as f:
            for line in f:
                cols = line.strip().split(',')
                if len(cols) >= 2:
                    lookup[cols[0].strip()] = cols[1].strip()
    except Exception as e:
        err_msg = f"Error reading index file {index_csv_path}: {e}"
        print(err_msg)
        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as ef:
            ef.write(err_msg + "\n")
        return 0

    # Process combined CSV file
    updated_rows = []
    matches_count = 0
    no_matches_count = 0
    
    try:
        with open(combined_csv_path, 'r', encoding='utf-8') as f:
            for line in f:
                cols = line.rstrip("\n").split(',')
                
                # Make sure there's a 6th column (index 5)
                if len(cols) > 5:
                    key = cols[5].strip()
                    if key in lookup:
                        cols[5] = lookup[key]
                        matches_count += 1
                    else:
                        no_matches_count += 1
                        
                updated_rows.append(','.join(cols) + "\n")
                
        # Write back to file
        with open(combined_csv_path, 'w', encoding='utf-8') as f:
            f.writelines(updated_rows)
            
    except Exception as e:
        err_msg = f"Error updating combined CSV {combined_csv_path} with index data: {e}"
        print(err_msg)
        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as ef:
            ef.write(err_msg + "\n")
        return 0
    
    msg = (f"Column updates complete. Matched {matches_count} entries from index file. "
           f"No matches for {no_matches_count} entries.")
    with open(LOG_FILE, "a", encoding="utf-8") as lf:
        lf.write(msg + "\n")
    print(msg)
    
    return matches_count

def main():
    global total_csv_found, global_raw_lines, global_filtered_lines, processed_csv_names, missing_date_archives, error_files
    
    # Reset global counters and lists
    total_csv_found = 0
    global_raw_lines = 0
    global_filtered_lines = 0
    processed_csv_names = []
    missing_date_archives = []
    error_files = set()
    
    # Setup output paths
    output_folder = results_dir
    os.makedirs(output_folder, exist_ok=True)
    
    # Define log files
    global LOG_FILE, ERROR_LOG_FILE
    LOG_FILE = os.path.join(output_folder, 'merge_log.txt')
    ERROR_LOG_FILE = os.path.join(output_folder, 'error_log.txt')
    
    # Remove previous logs if any
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    if os.path.exists(ERROR_LOG_FILE):
        os.remove(ERROR_LOG_FILE)
    
    global_input_lines = 0
    merged_files = []
    
    # Ensure extracted folder exists
    extracted_folder = os.path.join(base_folder, 'extracted')
    os.makedirs(extracted_folder, exist_ok=True)
    
    # Process compressed files
    for filename in os.listdir(base_folder):
        if filename.lower().endswith(('.zip', '.tar', '.tar.gz', '.tgz', '.7z')):
            file_path = os.path.join(base_folder, filename)
            merged_csv = os.path.join(extracted_folder, os.path.splitext(filename)[0] + '.csv')
            global_input_lines += merge_csv_from_compressed(file_path, merged_csv)
            add_date_column(merged_csv)
            merged_files.append(merged_csv)
    
    # Calculate total lines in merged files
    global_merged_lines = 0
    for mfile in merged_files:
        with open(mfile, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            global_merged_lines += len(lines)
    
    # Combine all CSV files into one
    combined_csv_path = os.path.join(output_folder, 'combined_results.csv')
    combined_lines = combine_all_csv_files(merged_files, combined_csv_path)
    
    # Update column 6 based on index_rigs.csv lookup
    index_csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets/index_rigs.csv')
    if os.path.exists(index_csv_path):
        matches = update_column_based_on_index(combined_csv_path, index_csv_path)
        print(f"Updated {matches} entries in the combined CSV file based on index file.")
    else:
        print(f"Warning: Index file {index_csv_path} not found. Column updates skipped.")
    
    # Summary reporting
    final_msg = (f"Final Summary:\n"
                 f"Total raw lines (before filtering): {global_raw_lines}\n"
                 f"Total lines after filtering: {global_filtered_lines}\n"
                 f"Total merged lines (final files): {global_merged_lines}\n"
                 f"Total lines in combined file: {combined_lines}\n"
                 f"Total CSV files processed: {total_csv_found}\n"
                 f"Global input lines (sum of filtered lines across archives): {global_input_lines}")
    with open(LOG_FILE, "a", encoding="utf-8") as lf:
        lf.write(final_msg + "\n")
    print(final_msg)
    
    print(f"Total CSV files found in compressed files: {total_csv_found}")
    print("Processed CSV files:")
    for name in processed_csv_names:
        print(f" - {name}")
    
    if missing_date_archives:
        print("\nArchives with missing date info:")
        for archive in missing_date_archives:
            print(f" - {archive}")
    else:
        print("\nNo archives with missing date info found.")
    
    # Verify date column insertion
    failed_files = []
    for mfile in merged_files:
        if not verify_date_column(mfile):
            failed_files.append(mfile)
    
    total_checked = len(merged_files)
    verification_summary = (f"Verification Summary: {total_checked} files checked. "
                            f"{len(failed_files)} files failed verification.")
    with open(LOG_FILE, "a", encoding="utf-8") as lf:
        lf.write(verification_summary + "\n")
    print(verification_summary)
    
    for ffile in failed_files:
        fail_msg = f"Error: {ffile} does not have correct date column ({extract_date(ffile)})"
        with open(LOG_FILE, "a", encoding="utf-8") as lf:
            lf.write(fail_msg + "\n")
        print(fail_msg)

if __name__ == '__main__':
    main()
