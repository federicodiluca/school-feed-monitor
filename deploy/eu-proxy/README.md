# Ponte europeo (Cloud Run)

Serve solo a questo: alcune fonti italiane non rispondono agli indirizzi IP esteri, e la VM
del servizio sta negli Stati Uniti. Questo micro-servizio gira in Europa, scarica quelle
pagine e le passa alla VM. Rientra nel free tier di Cloud Run (2 milioni di richieste al
mese; noi ne facciamo ~170 al giorno).

Non è un proxy aperto: risponde solo per i domini elencati e solo con la chiave condivisa.

## Deploy (dal tuo PC o dalla VM, una volta sola)

```bash
cd deploy/eu-proxy

# chiave condivisa: generala e tienila da parte
python3 -c "import secrets; print(secrets.token_urlsafe(24))"

gcloud run deploy sfm-eu-proxy \
  --source . \
  --region europe-west8 \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 1 \
  --memory 256Mi \
  --set-env-vars "^@^ALLOWED_HOSTS=istruzione.calabria.it,uspmc.sinp.net@PROXY_KEY=LA-CHIAVE-GENERATA"
```

Quel `^@^` iniziale non è un refuso: dice a `gcloud` di separare le variabili con `@` invece
che con la virgola, che qui serve dentro `ALLOWED_HOSTS`. Senza, `gcloud` risponde
*"Bad syntax for dict arg"*. In alternativa, un file (ricordati che contiene la chiave:
non committarlo):

```bash
cat > /tmp/proxy-env.yaml <<'YAML'
ALLOWED_HOSTS: "istruzione.calabria.it,uspmc.sinp.net"
PROXY_KEY: "LA-CHIAVE-GENERATA"
YAML
gcloud run deploy sfm-eu-proxy --source . --region europe-west8   --allow-unauthenticated --min-instances 0 --max-instances 1 --memory 256Mi   --env-vars-file /tmp/proxy-env.yaml
rm /tmp/proxy-env.yaml
```

`europe-west8` è Milano; va bene anche `europe-west1` (Belgio). Al termine `gcloud` stampa
l'URL del servizio, tipo `https://sfm-eu-proxy-xxxxx.europe-west8.run.app`.

Prova:

```bash
curl -s https://sfm-eu-proxy-xxxxx.europe-west8.run.app/health
curl -s -H "X-Sfm-Key: LA-CHIAVE" \
  "https://sfm-eu-proxy-xxxxx.europe-west8.run.app/fetch?url=https://www.istruzione.calabria.it/feed/" | head -c 200
```

## Collegarlo al bot

Sulla VM, in `/opt/sfm/.env`:

```ini
SFM_FETCH_PROXY=https://sfm-eu-proxy-xxxxx.europe-west8.run.app
SFM_FETCH_PROXY_KEY=LA-CHIAVE-GENERATA
SFM_FETCH_PROXY_HOSTS=istruzione.calabria.it,uspmc.sinp.net
```

Poi `sudo systemctl restart sfm-bot`. I domini elencati passano **sempre** dal ponte (così non
si aspettano 20 secondi di timeout a vuoto); per tutti gli altri il ponte viene usato solo
come seconda possibilità, se la lettura diretta fallisce.

Verifica dalla VM:

```bash
cd /opt/sfm && .venv/bin/python -c "
from sfm.source_parser import fetch_url
data, ct = fetch_url('https://www.istruzione.calabria.it/feed/')
print(len(data), 'byte', ct)
"
```

## Costi

Cloud Run fattura solo mentre una richiesta è in corso, con `--min-instances 0` non resta
niente acceso. Le nostre ~5.000 richieste al mese stanno dentro il free tier. Se un giorno
non servisse più: `gcloud run services delete sfm-eu-proxy --region europe-west8`.
