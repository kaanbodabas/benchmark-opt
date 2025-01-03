from problems.maxcut import Maxcut
from utils import data, run
import maps

solvers = maps.get_solvers("SDP")
csv_filename = "maxcut"
num_instances = 10000
laplacian_matrices = []
for _ in range(num_instances):
    laplacian_matrices.append(data.get_random_weighted_graph(40, 0.5, 0, 30))
plot_title = "Maxcut"

run.start(solvers, csv_filename, Maxcut, (laplacian_matrices,))
run.results(csv_filename, solvers, num_instances, plot_title)