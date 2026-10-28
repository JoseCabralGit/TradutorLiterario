import os
import io
import pickle
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.pickle'

def get_drive_service():
    """Autentica e retorna o serviço da API do Google Drive."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)
            
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Arquivo '{CREDENTIALS_FILE}' não encontrado! "
                    "Para usar o Google Drive, coloque as credenciais OAuth do Google Cloud em 'credentials.json'."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)
            
    return build('drive', 'v3', credentials=creds)

def download_excel_from_gdrive(file_id_or_link: str, output_path: str = "temp_gdrive_download.xlsx") -> str:
    """Baixa um arquivo do Google Drive por ID ou link direto para um arquivo Excel temporário."""
    # Extrair ID caso seja um link completo do Google Drive
    file_id = file_id_or_link.strip()
    if "drive.google.com" in file_id:
        if "/d/" in file_id:
            parts = file_id.split("/d/")
            file_id = parts[1].split("/")[0]
        elif "id=" in file_id:
            parts = file_id.split("id=")
            file_id = parts[1].split("&")[0]

    service = get_drive_service()
    
    # Verificar se é uma planilha do Google Sheets e exportar como Excel, ou baixar binário direto
    try:
        file_meta = service.files().get(fileId=file_id, fields="mimeType, name").execute()
        mime_type = file_meta.get('mimeType', '')
        
        request = None
        if mime_type == 'application/vnd.google-apps.spreadsheet':
            # Exportar Google Sheets para Excel (.xlsx)
            request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        else:
            # Download direto para arquivo binário (.xlsx)
            request = service.files().get_media(fileId=file_id)

        fh = io.FileIO(output_path, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            
        return output_path
    except Exception as e:
        raise RuntimeError(f"Erro ao baixar arquivo do Google Drive: {e}")
