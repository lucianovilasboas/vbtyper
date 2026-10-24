# Instalar o VB Typer no Linux Mint Cinnamon

O instalador configura o **cliente desktop** no usuário atual. O backend continua
rodando no host ou VPS que já o administra. O cliente grava e insere o texto
nesta máquina; o áudio segue pela rede até a API, pelo domínio HTTPS ou pela VPN.

## Requisitos

- Linux Mint Cinnamon em sessão X11;
- acesso ao domínio HTTPS do servidor ou à rede ZeroTier/Tailscale;
- token Bearer válido da API;
- conexão à internet durante a instalação, para dependências do sistema e do
  cliente.

## Instalar

No terminal, na raiz deste repositório:

```bash
# Domínio HTTPS (padrão): https://vbtyper.lucianovilasboas.com.br
./scripts/install-linux-mint.sh

# Endpoints alternativos:
./scripts/install-linux-mint.sh --zerotier
./scripts/install-linux-mint.sh --tailscale
```

O instalador solicita o token sem mostrá-lo na tela e grava-o em
`~/.config/vb-typer/api-token` com permissão `0600`. Para apontar para outro
endereço, use `./scripts/install-linux-mint.sh --backend-url
https://servidor.exemplo:8444`.

O cliente inicia no login e aparece no menu de aplicativos como **VB Typer**.
Segure **Ctrl+Super** para gravar e solte para transcrever e inserir o texto no
cursor local. O serviço pode ser acompanhado com:

```bash
systemctl --user status vb-typer-desktop
journalctl --user -u vb-typer-desktop -f
```

Para remover cliente, serviço, atalho e ícone:

```bash
~/.local/share/vb-typer-app/scripts/install-linux-mint.sh --uninstall
```

O token e as preferências em `~/.config/vb-typer/` são preservados.

O instalador instala `libasound2-plugins`, necessário para o `arecord` acessar
PulseAudio/PipeWire. Se o ditado mostrar erro de dispositivo de áudio em uma
instalação anterior, atualize o cliente executando novamente o instalador. Para
corrigir apenas essa dependência, rode:

```bash
sudo apt update
sudo apt install libasound2-plugins
systemctl --user restart vb-typer-desktop
```

Se continuar falhando, confira se o servidor de áudio da sessão está ativo com
`pactl info` e rode `vb-typer-desktop --self-test`; o autoteste verifica se o
dispositivo Pulse do ALSA está disponível sem gravar áudio.

## Executar pelo AppImage

Também é possível usar o cliente sem instalar o serviço nem criar atalho. O
AppImage pronto fica em `dist/VB-Typer-0.1.6-x86_64.AppImage`; gere-o com
`./scripts/build-appimage.sh` (requer `uv`, internet no primeiro build e o
[`appimagetool`](https://github.com/AppImage/appimagetool/releases/continuous)).

```bash
chmod +x dist/VB-Typer-0.1.6-x86_64.AppImage
./dist/VB-Typer-0.1.6-x86_64.AppImage
```

O AppImage usa o domínio HTTPS por padrão. Para usar outro servidor, passe a
URL ao executar; por exemplo, Tailscale:

```bash
./dist/VB-Typer-0.1.6-x86_64.AppImage \
  --base-url https://xps.tail5ae70d.ts.net:8444
```

Se o FUSE não estiver disponível, use
`APPIMAGE_EXTRACT_AND_RUN=1 ./dist/VB-Typer-0.1.6-x86_64.AppImage` (acrescente
`--base-url` depois do nome, se necessário). O token deve existir em
`~/.config/vb-typer/api-token` com permissão `0600`; os helpers GTK e `arecord`
continuam usando as bibliotecas e os programas fornecidos pelo Linux Mint. Se
ainda não tiver token salvo, grave-o sem exibi-lo no terminal:

```bash
install -d -m 700 ~/.config/vb-typer
read -rsp 'Token Bearer do VB Typer: ' vb_typer_api_token
printf '\n'
printf '%s\n' "$vb_typer_api_token" > ~/.config/vb-typer/api-token
chmod 600 ~/.config/vb-typer/api-token
unset vb_typer_api_token
```

O token não é empacotado no AppImage; cada máquina precisa guardar seu token
localmente. O backend e o proxy HTTPS também precisam aceitar o hostname
`vbtyper.lucianovilasboas.com.br`.

## Configuração do servidor Tailscale

O endpoint `https://xps.tail5ae70d.ts.net:8444` precisa encaminhar as requisições
à API VB Typer. No arquivo de ambiente **do backend**, permita o hostname em
`VB_TYPER_ALLOWED_HOSTS` e a origem completa em `VB_TYPER_CORS_ORIGINS`:

```ini
VB_TYPER_ALLOWED_HOSTS=127.0.0.1,localhost,10.147.20.2,xps.tail5ae70d.ts.net
VB_TYPER_CORS_ORIGINS=http://10.147.20.2:8766,https://xps.tail5ae70d.ts.net:8444
```

Mantenha `VB_TYPER_BIND_ADDR` restrito ao endereço privado configurado no host.
Se o endpoint HTTPS usa proxy ou encaminhamento Tailscale, esse proxy deve
conseguir alcançar a porta publicada pela API. Depois de editar o ambiente,
recrie o contêiner para aplicar os valores:

```bash
cd deploy/docker
docker compose up -d --force-recreate
```

O cliente desktop nativo não envia `Origin`; a configuração de CORS é necessária
para abrir e usar a interface web no navegador pelo endpoint Tailscale.
