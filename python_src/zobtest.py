import random


def generate_zobrist_cpp():
    # Fixer la graine pour garantir la reproductibilité
    random.seed(123456789)

    def gen_hex64():
        # Génère un entier de 64 bits et le formate en hexadécimal C++
        return f"0x{random.getrandbits(64):016X}ULL"

    cpp_content = '#include "zobrist.hpp"\n\n'
    cpp_content += 'namespace Zobrist {\n\n'

    # 1. PIECE_KEYS [64 cases][12 types de pièces (6 blancs, 6 noirs)]
    cpp_content += '    const uint64_t PIECE_KEYS[64][12] = {\n'
    for _ in range(64):
        row = [gen_hex64() for _ in range(12)]
        cpp_content += '        { ' + ', '.join(row) + ' },\n'
    cpp_content += '    };\n\n'

    # 2. BLACK_TO_MOVE (1 constante)
    cpp_content += f'    const uint64_t BLACK_TO_MOVE = {gen_hex64()};\n\n'

    # 3. CASTLING_KEYS (16 combinaisons possibles pour les 4 droits de roque)
    cpp_content += '    const uint64_t CASTLING_KEYS[16] = {\n        '
    castling_keys = [gen_hex64() for _ in range(16)]
    cpp_content += ',\n        '.join(castling_keys)
    cpp_content += '\n    };\n\n'

    # 4. EN_PASSANT_KEYS (8 colonnes possibles)
    cpp_content += '    const uint64_t EN_PASSANT_KEYS[8] = {\n        '
    ep_keys = [gen_hex64() for _ in range(8)]
    cpp_content += ', '.join(ep_keys)
    cpp_content += '\n    };\n\n'

    cpp_content += '}\n'

    # Écriture dans le fichier
    with open('zobrist.cpp', 'w') as f:
        f.write(cpp_content)

    print("Fichier zobrist.cpp généré avec succès.")


if __name__ == "__main__":
    generate_zobrist_cpp()