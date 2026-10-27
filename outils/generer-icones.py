# Rend toutes les icônes de l'appli depuis icons/icon.svg (source unique).
# Chaque taille est rendue par Inkscape à sa résolution exacte (jamais un petit PNG agrandi).
#   - icon-<n>.png        : carré arrondi, coins transparents (PC, Android)
#   - maskable-<n>.png    : fond plein bord à bord (Android, zone de sécurité respectée par le dessin)
#   - apple-touch-icon.png: fond plein 180 px (iPhone : iOS arrondit lui-même)
#   - favicon.ico         : 16/32/48 pour l'onglet du navigateur
# Usage : python outils/generer-icones.py [--apercu]
import os, subprocess, sys, tempfile
from PIL import Image

INKSCAPE = r'C:\Program Files\Inkscape\bin\inkscape.exe'
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER = os.path.join(RACINE, 'icons')
SOURCE = os.path.join(DOSSIER, 'icon.svg')
TAILLES = [16, 32, 48, 72, 96, 128, 144, 192, 256, 512]


def rendre(svg, taille, sortie):
    subprocess.run([INKSCAPE, svg, '--export-type=png', f'--export-filename={sortie}',
                    '-w', str(taille), '-h', str(taille)], check=True, capture_output=True)
    return Image.open(sortie).convert('RGBA')


def main():
    tmp = tempfile.mkdtemp(prefix='icones-opr-')
    with open(SOURCE, encoding='utf-8') as f:
        svg = f.read()
    plein = os.path.join(tmp, 'plein.svg')
    with open(plein, 'w', encoding='utf-8') as f:
        f.write(svg.replace('rx="112"', 'rx="0"', 1))

    if '--apercu' in sys.argv:
        for t in (512, 48, 32, 16):
            print('apercu :', rendre(SOURCE, t, os.path.join(tmp, f'apercu-{t}.png')) and os.path.join(tmp, f'apercu-{t}.png'))
        return

    images = {}
    for t in TAILLES:
        sortie = os.path.join(DOSSIER, f'icon-{t}.png')
        images[t] = rendre(SOURCE, t, sortie)
    for t in (192, 512):
        rendre(plein, t, os.path.join(DOSSIER, f'maskable-{t}.png'))
    rendre(plein, 180, os.path.join(DOSSIER, 'apple-touch-icon.png'))
    ico = os.path.join(DOSSIER, 'favicon.ico')
    images[48].save(ico, format='ICO', sizes=[(16, 16), (32, 32), (48, 48)],
                    append_images=[images[16], images[32]])
    print('icônes écrites dans', DOSSIER, ':', sorted(os.listdir(DOSSIER)))


if __name__ == '__main__':
    main()
