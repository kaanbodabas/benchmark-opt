from problems.image_deblurring import ImageDeblurring
from enums import Solver, get_qp_solvers
from utils import data, verify
import pandas as pd

def check_optimality(problem, solver, eps):
    if not verify.is_qp_solution_optimal(problem, solver, eps):
        print(f"Solver {solver} reports an inaccurate primal-dual solution!")
        return False
    return True

def run_image_deblurring(blur_matrix_infos, images, rhos, csv_filename, solvers=get_qp_solvers(), eps=(10**-5, 10**-5, 10**-5)):
    # blur_matrix_infos is a set of tuples
    # images is a set of images ready to be passed to the problem
    # rhos is a set of rhos ready to be passed to the problem
    # this generates len(images) x len(rhos) many problem instances

    solutions = []

    for blur_matrix_info, x in zip(blur_matrix_infos, images):
        for rho in rhos:
            A = data.get_2D_blur_matrix(*blur_matrix_info)
            problem = ImageDeblurring(A, x, rho)
            problem.canonicalize()

            for solver in solvers:
                solution = problem.solve(solver)

                if check_optimality(problem, solver, eps):
                    solutions.append({"Solver": solver, "Solve Time": solution.solve_time})
                else:
                    # TODO: Handle when solvers fail
                    solutions.append({"Solver": solver, "Solve Time": "fail"})
        
    pd.DataFrame(solutions, dtype=object).to_csv(f"output/{csv_filename}.csv")