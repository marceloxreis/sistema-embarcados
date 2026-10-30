"""Garante que nenhum texto do LCD 16x2 do Mega passe de 16 colunas (MEGA-07).

Os textos são extraídos do próprio .ino: literais de notice(...), atribuições a/b
da tela (displayTick), lcd.print e o rótulo de LCD de failEnrollment(codigo, rotulo).
O código de auditoria (primeiro argumento de failEnrollment) precisa continuar
existindo em reasonNames, porque é o que a CAM e o servidor reconhecem.
"""
import re
import unittest
from pathlib import Path

MEGA = Path(__file__).resolve().parents[1] / 'firmware/MegaControlador'
COLUNAS = 16
TAMANHO_ID = len('ID 000')  # idText() sempre produz 6 caracteres
LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')


def literais(texto):
    return LITERAL.findall(texto)


def argumentos(fonte, nome):
    """Devolve o texto entre parênteses de cada chamada `nome(...)`, respeitando strings."""
    for m in re.finditer(r'\b%s\(' % re.escape(nome), fonte):
        if fonte[:m.start()].rstrip().endswith('void'):  # definição, não chamada
            continue
        i = inicio = m.end()
        profundidade = 1
        while profundidade:
            c = fonte[i]
            if c == '"':
                i += 1
                while fonte[i] != '"':
                    i += 2 if fonte[i] == '\\' else 1
            elif c == '(':
                profundidade += 1
            elif c == ')':
                profundidade -= 1
            i += 1
        yield fonte[inicio:i - 1]


class LcdTextosTests(unittest.TestCase):
    def setUp(self):
        self.sketch = (MEGA / 'MegaControlador.ino').read_text()

    def test_notice_cabe_no_lcd(self):
        encontrados = [t for chamada in argumentos(self.sketch, 'notice') for t in literais(chamada)]
        self.assertGreaterEqual(len(encontrados), 20, 'extração de notice(...) falhou')
        longos = [t for t in encontrados if len(t) > COLUNAS]
        self.assertEqual(longos, [], 'textos de notice(...) com mais de 16 colunas')

    def test_linhas_da_tela_cabem_no_lcd(self):
        inicio = self.sketch.index('void displayTick()')
        corpo = self.sketch[inicio:self.sketch.index('// Lista circular', inicio)]
        atribuicoes = re.findall(r'\b([ab])\s*=\s*([^;]+);', corpo)
        self.assertGreaterEqual(len(atribuicoes), 15, 'extração das linhas a/b falhou')
        longos = []
        for _, expressao in atribuicoes:
            # idText(...) concatenado a um sufixo: pior caso são 6 colunas do ID a mais.
            extra = TAMANHO_ID if 'idText(' in expressao and '+' in expressao else 0
            for t in literais(expressao):
                if len(t) + extra > COLUNAS:
                    longos.append(t)
        self.assertEqual(longos, [], 'linhas a/b da tela com mais de 16 colunas')

    def test_lcd_print_cabe_no_lcd(self):
        textos = [t for chamada in argumentos(self.sketch, 'lcd.print') for t in literais(chamada)]
        self.assertTrue(textos, 'extração de lcd.print falhou')
        self.assertEqual([t for t in textos if len(t) > COLUNAS], [])

    def test_fail_enrollment_separa_auditoria_de_lcd(self):
        codigos_bloco = re.search(r'reasonNames\[\] = \{(.*?)\};', self.sketch).group(1)
        codigos = set(literais(codigos_bloco))
        chamadas = [literais(c) for c in argumentos(self.sketch, 'failEnrollment')]
        self.assertGreaterEqual(len(chamadas), 10, 'extração de failEnrollment falhou')
        for lits in chamadas:
            self.assertEqual(len(lits), 2, 'failEnrollment deve receber codigo de auditoria e rotulo de LCD')
            codigo, rotulo = lits
            self.assertIn(codigo, codigos, 'código de auditoria fora de reasonNames: %r' % codigo)
            self.assertLessEqual(len(rotulo), COLUNAS, 'rótulo de LCD com mais de 16 colunas: %r' % rotulo)


if __name__ == '__main__':
    unittest.main()
