import requests
import json
import argparse
import chess
import math
import sys
from urllib import parse


def get_moves(epd):

    api = "http://www.chessdb.cn/cdb.php"
    timeout = 3

    parameters = {"action": "queryall", "board": epd, "json": 1}

    moves = []

    try:
        response = requests.get(api, parameters, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        if data["status"] == "ok":
            moves = data["moves"]
        elif data["status"] == "unknown":
            pass
        elif data["status"] == "rate limited exceeded":
            pass
        else:
            sys.stderr.write(data)
    except:
        pass

    stdmoves = []
    for m in moves:
        stdmoves.append({"score": m["score"], "uci": m["uci"]})

    return stdmoves


class ChessGraph:
    def __init__(self):
        self.visited = set()

    def write_node(self, board, score, showboard, pvNode):

        if board.turn == chess.WHITE:
            color = ", color=gold, shape=box"
        else:
            color = ", color=burlywood4, shape=box"

        if pvNode:
            width = ", penwidth=3"
        else:
            width = ", penwidth=1"

        epd = board.epd()
        url = ', URL="https://www.chessdb.cn/queryc_en/?' + parse.quote(epd) + '"'
        if showboard:
            label = (
                'fontname="Courier", label="'
                + board.unicode(empty_square="\u00B7")
                + '"'
            )
        else:
            label = 'label="' + str(score) + '"'

        return '"' + epd + '" [' + label + color + url + width + "]"

    def write_edge(self, epdfrom, epdto, move, turn, pvEdge):

        if turn == chess.WHITE:
            color = ", color=gold"
        else:
            color = ", color=burlywood4"

        if pvEdge:
            width = ', penwidth=3, fontname="Helvetica-bold"'
        else:
            width = ', penwidth=1, fontname="Helvectica"'

        return (
            '"'
            + epdfrom
            + '" -> "'
            + epdto
            + '" [label="'
            + move
            + '"'
            + color
            + width
            + "]"
        )

    def recurse(self, board, depth, alpha, beta, pvNode):

        # terminate recursion

        returnstr = []

        epdfrom = board.epd()
        self.visited.add(epdfrom)
        turn = board.turn
        moves = get_moves(epdfrom)
        bestscore = None
        edgesfound = 0
        edgesdrawn = 0

        # loop through the moves that are within delta of the bestmove
        for m in sorted(moves, key=lambda item: item["score"], reverse=True):

            score = int(m["score"])

            if bestscore == None:
                bestscore = score

            if score <= alpha:
                break

            ucimove = m["uci"]
            move = chess.Move.from_uci(ucimove)
            sanmove = board.san(move)
            board.push(move)
            epdto = board.epd()
            edgesfound += 1

            # no loops, otherwise recurse
            newDepth = depth - int(1.5 + math.log(edgesfound) / math.log(2))

            if newDepth > 0:
                pvEdge = pvNode and score == bestscore
                if not epdto in self.visited:
                    returnstr += self.recurse(
                        board, newDepth, -beta, -alpha, pvNode=pvEdge
                    )

                edgesdrawn += 1
                returnstr.append(self.write_edge(epdfrom, epdto, sanmove, turn, pvEdge))

            board.pop()

        returnstr.append(self.write_node(board, bestscore, edgesdrawn > 2, pvNode))

        return returnstr

    def generate_graph(self, epd, depth, alpha, beta):

        # set initial board
        board = chess.Board(epd)

        dotstr = ["digraph {"]
        dotstr += self.recurse(board, depth, alpha, beta, pvNode=True)
        dotstr.append(self.write_node(board, 0, True, True))
        dotstr.append("}")

        return dotstr


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--depth",
        type=int,
        default=6,
        help="Maximum depth (in plies) of a followed variation",
    )

    parser.add_argument(
        "--alpha",
        type=int,
        default=0,
        help="Lower bound on the score of variations to be followed",
    )

    parser.add_argument(
        "--beta",
        type=int,
        default=15,
        help="Upper bound on the score of variations to be followed",
    )

    parser.add_argument(
        "--position",
        type=str,
        default="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        help="FEN of the starting position.",
    )

    args = parser.parse_args()

    chessgraph = ChessGraph()

    # generate the content of the dotfile
    dotstr = chessgraph.generate_graph(args.position, args.depth, args.alpha, args.beta)

    # write it
    for line in dotstr:
        print(line)
