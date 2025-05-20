import sys
import sqlite3
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon import errors as telethon_errors

def _mostrar_aviso() -> None:
    print(
        "\n―― ⚠️ AVISO: Criar sessões frequentemente e solicitar OTPs pode aumentar o risco de "
        "sua conta ser temporariamente ou permanentemente banida."
        "\n―― O Telegram monitora atividades incomuns, como várias tentativas de login em um curto período de tempo."
        "\n―― Seja cauteloso e evite criar muitas sessões rapidamente."
        "\n―― ℹ️ Termos de Serviço do Telegram: https://core.telegram.org/api/terms"
        "\n―― ℹ️ FAQ do Telethon: "
        "https://docs.telethon.dev/en/stable/quick-references/faq.html#my-account-was-deleted-limited-when-using-the-library\n")

def criar_sessao_telethon(api_id: int = None, api_hash: str = None, telefone: str = None) -> None:
    _mostrar_aviso()

    usuario_api_id = api_id or int(input("Digite seu API ID: "))
    usuario_api_hash = api_hash or input("Digite seu API HASH: ")
    usuario_telefone = telefone or input("Digite seu número de telefone (ex: +1234567890): ")

    try:
        # Inicializa o cliente do Telegram com o arquivo de sessão
        client = TelegramClient(f'{usuario_telefone}.session', usuario_api_id, usuario_api_hash)
        client.connect()

        # Verifica se o usuário está autorizado
        if not client.is_user_authorized():
            client.send_code_request(usuario_telefone)
            try:
                # Solicita o código enviado para o telefone
                client.sign_in(usuario_telefone, input("Digite o código enviado para seu telefone: "))
            except telethon_errors.SessionPasswordNeededError:
                # Solicita a senha 2FA se necessário
                client.sign_in(password=input("Digite a senha da Verificação em Duas Etapas (2FA): "))
    except sqlite3.OperationalError:
        print(
            "\n―― ❌ O arquivo de sessão fornecido não pôde ser aberto. "
            "Esse problema pode ocorrer se o arquivo de sessão foi criado usando uma biblioteca diferente ou está corrompido. "
            "Por favor, certifique-se de que o arquivo de sessão é compatível com o Telethon."
        )
        sys.exit(1)
    except telethon_errors.RPCError as e:
        print(f"\n―― ❌ Ocorreu um erro RPC: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n―― ❌ Ocorreu um erro inesperado: {e}")
        sys.exit(1)

    # Exibe informações sobre a sessão criada
    print(
        f"\n―― 🟢 SESSÃO TELETHON ↓"
        f"\n―― ✨ ARQUIVO DE SESSÃO salvo como `{usuario_telefone}{'.session' if not usuario_telefone.endswith('.session') else ''}`"
        f"\n―― ✨ SESSÃO EM STRING: {StringSession.save(client.session)}"
    )

    client.disconnect()

if __name__ == "__main__":
    criar_sessao_telethon()
