import requests
import platform
import argparse
import chess
import chess.engine
import chess.svg
import math
import sys
import concurrent.futures
import multiprocessing
import copy
import hashlib
import cairosvg
import graphviz
from urllib import parse


class ChessGraph:
    def __init__(
        self,
        depth,
        concurrency,
        source,
        engine,
        enginedepth,
        maxmoves,
        boardstyle,
        boardedges,
    ):
        self.visited = set()
        self.depth = depth
        self.executorgraph = [
            concurrent.futures.ThreadPoolExecutor(max_workers=concurrency)
            for i in range(0, depth + 1)
        ]
        self.executorwork = concurrent.futures.ThreadPoolExecutor(
            max_workers=concurrency
        )
        self.session = requests.Session()
        self.source = source
        self.engine = engine
        self.enginedepth = enginedepth
        self.enginemaxmoves = maxmoves
        self.boardstyle = boardstyle
        self.boardedges = boardedges
        self.graph = graphviz.Digraph("ChessGraph", format="svg")

    def get_moves(self, epd):

        if self.source == "chessdb":
            return self.get_moves_chessdb(epd)
        elif self.source == "engine":
            return self.get_moves_engine(epd)
        else:
            assert False

    def get_moves_engine(self, epd):

        moves = []
        engine = chess.engine.SimpleEngine.popen_uci(self.engine)
        board = chess.Board(epd)
        info = engine.analyse(
            board,
            chess.engine.Limit(depth=self.enginedepth),
            multipv=self.enginemaxmoves,
            info=chess.engine.INFO_SCORE | chess.engine.INFO_PV,
        )
        engine.quit()
        for i in info:
            moves.append(
                {
                    "score": i["score"].pov(board.turn).score(mate_score=30000),
                    "uci": chess.Move.uci(i["pv"][0]),
                }
            )

        return moves

    def get_moves_chessdb(self, epd):

        api = "http://www.chessdb.cn/cdb.php"
        url = api + "?action=queryall&board=" + parse.quote(epd) + "&json=1"
        timeout = 3

        moves = []

        try:
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            if data["status"] == "ok":
                moves = data["moves"]
            elif data["status"] == "unknown":
                pass
            elif data["status"] == "rate limited exceeded":
                sys.stderr.write("rate")
            else:
                sys.stderr.write(data)
        except:
            pass

        stdmoves = []
        for m in moves:
            stdmoves.append({"score": m["score"], "uci": m["uci"]})

        return stdmoves

    def write_node(self, board, score, showboard, pvNode, tooltip):

        epd = board.epd()

        color = "gold" if board.turn == chess.WHITE else "burlywood4"
        penwidth = "3" if pvNode else "1"

        epdweb = parse.quote(epd)
        URL = "https://www.chessdb.cn/queryc_en/?" + epdweb
        image = None

        if showboard and not self.boardstyle == "none":
            if self.boardstyle == "unicode":
                label = board.unicode(empty_square="\u00B7")
            elif self.boardstyle == "svg":
                filename = (
                    "node-" + hashlib.sha256(epd.encode("utf-8")).hexdigest() + ".svg"
                )
                cairosvg.svg2svg(
                    bytestring=chess.svg.board(board, size="200px").encode("utf-8"),
                    write_to=filename,
                )
                image = filename
                label = ""
        else:
            label = str(score if board.turn == chess.WHITE else -score)

        if image:
            self.graph.node(
                epd,
                label=label,
                shape="box",
                color=color,
                penwidth=penwidth,
                URL=URL,
                image=image,
                tooltip=tooltip,
            )
        else:
            self.graph.node(
                epd,
                label=label,
                shape="box",
                color=color,
                penwidth=penwidth,
                fontname="Courier",
                URL=URL,
                tooltip=tooltip,
            )

    def write_edge(
        self, epdfrom, epdto, sanmove, ucimove, turn, score, pvEdge, lateEdge
    ):

        color = "gold" if turn == chess.WHITE else "burlywood4"
        penwidth = "3" if pvEdge else "1"
        fontname = "Helvetica-bold" if pvEdge else "Helvectica"
        style = "dashed" if lateEdge else "solid"
        labeltooltip = "{} ({}) : {}".format(
            sanmove, ucimove, str(score if turn == chess.WHITE else -score)
        )
        tooltip = labeltooltip
        self.graph.edge(
            epdfrom,
            epdto,
            label=sanmove,
            color=color,
            penwidth=penwidth,
            fontname=fontname,
            tooltip=tooltip,
            labeltooltip=labeltooltip,
            style=style,
        )

    def recurse(self, board, depth, alpha, beta, pvNode, plyFromRoot):

        epdfrom = board.epd()

        # terminate recursion if visited
        if epdfrom in self.visited:
            return
        else:
            self.visited.add(epdfrom)

        if board.is_checkmate():
            moves = []
            bestscore = -30000
        elif board.is_stalemate():
            moves = []
            bestscore = 0
        else:
            moves = self.executorwork.submit(self.get_moves, epdfrom).result()
            bestscore = None

        edgesfound = 0
        edgesdrawn = 0
        futures = []
        turn = board.turn
        tooltip = epdfrom+'\n'

        # loop through the moves that are within delta of the bestmove
        for m in sorted(moves, key=lambda item: item["score"], reverse=True):

            score = int(m["score"])

            if bestscore is None:
                bestscore = score

            if score <= alpha:
                break

            ucimove = m["uci"]
            move = chess.Move.from_uci(ucimove)
            sanmove = board.san(move)
            board.push(move)
            epdto = board.epd()
            edgesfound += 1
            pvEdge = pvNode and score == bestscore
            lateEdge = score != bestscore

            # no loops, otherwise recurse
            if score == bestscore:
                newDepth = depth - 1
            else:
                newDepth = depth - int(1.5 + math.log(edgesfound) / math.log(2))

            if newDepth >= 0:
                if epdto not in self.visited:
                    futures.append(
                        self.executorgraph[depth].submit(
                            self.recurse,
                            copy.deepcopy(board),
                            newDepth,
                            -beta,
                            -alpha,
                            pvEdge,
                            plyFromRoot + 1,
                        )
                    )
                edgesdrawn += 1
                tooltip += "{} : {}\n".format(sanmove, str(score if turn == chess.WHITE else -score))
                self.write_edge(
                    epdfrom, epdto, sanmove, ucimove, turn, score, pvEdge, lateEdge
                )

            board.pop()

        concurrent.futures.wait(futures)

        remainingMoves = len(moves) - edgesdrawn
        tooltip += "{} remaining {}\n".format(remainingMoves, "move" if remainingMoves == 1 else "moves")

        if edgesdrawn == 0:
           tooltip += "terminal: {}".format(str(bestscore if turn == chess.WHITE else -bestscore))

        self.write_node(
            board,
            bestscore,
            edgesdrawn >= self.boardedges
            or (pvNode and edgesdrawn == 0)
            or plyFromRoot == 0,
            pvNode,
            tooltip,
        )

    def generate_graph(self, epd, alpha, beta):

        # set initial board
        board = chess.Board(epd)

        if board.turn == chess.WHITE:
            initialAlpha, initialBeta = alpha, beta
        else:
            initialAlpha, initialBeta = -beta, -alpha

        self.recurse(
            board, self.depth, initialAlpha, initialBeta, pvNode=True, plyFromRoot=0
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="An utility to create a graph of moves from a specified chess position. ",
    )

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
        help="Lower bound on the score of variations to be followed (for white)",
    )

    parser.add_argument(
        "--beta",
        type=int,
        default=15,
        help="Lower bound on the score of variations to be followed (for black)",
    )

    parser.add_argument(
        "--concurrency",
        type=int,
        default=multiprocessing.cpu_count(),
        help="Number of cores to use for work / requests.",
    )

    parser.add_argument(
        "--position",
        type=str,
        default="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        help="FEN of the starting position.",
    )

    parser.add_argument(
        "--source",
        choices=["chessdb", "engine"],
        type=str,
        default="chessdb",
        help="Use chessdb or engine to score and rank moves",
    )

    parser.add_argument(
        "--boardstyle",
        choices=["unicode", "svg", "none"],
        type=str,
        default="unicode",
        help="Which style to use to visualize a board.",
    )

    parser.add_argument(
        "--boardedges",
        type=int,
        default=3,
        help="Minimum number of edges needed before a board is visualized in the node.",
    )

    parser.add_argument(
        "--engine",
        type=str,
        default="stockfish.exe"
        if "windows" in platform.system().lower()
        else "stockfish",
        help="Name of the engine binary (with path as needed).",
    )

    parser.add_argument(
        "--enginedepth",
        type=int,
        default=20,
        help="Depth of the search used by the engine in evaluation",
    )

    parser.add_argument(
        "--enginemaxmoves",
        type=int,
        default=10,
        help="Maximum number of moves (MultiPV) considered by the engine in evaluation",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="chess.svg",
        help="Name of the output file (image in .svg format).",
    )

    parser.add_argument(
        "--embed",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="If the individual svg boards should be embedded in the final .svg image. Unfortunately URLs are not preserved.",
    )

    args = parser.parse_args()

    chessgraph = ChessGraph(
        args.depth,
        args.concurrency,
        args.source,
        args.engine,
        args.enginedepth,
        args.enginemaxmoves,
        args.boardstyle,
        args.boardedges,
    )

    # generate the content of the dotfile
    chessgraph.generate_graph(args.position, args.alpha, args.beta)

    # generate the svg image (calls graphviz under the hood)
    svgpiped = chessgraph.graph.pipe()

    if args.embed:
        # this embeds the images of the boards generated.
        # Unfortunately, does remove the URLs that link to chessdb.
        # probably some smarter manipulation directly on the xml
        # would also allow to shrink the image size (each board embeds pieces etc.)
        cairosvg.svg2svg(
            bytestring=svgpiped,
            write_to=args.output,
        )
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(svgpiped.decode("utf-8"))
