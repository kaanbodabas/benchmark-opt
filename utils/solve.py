from scipy import sparse
import gurobipy as gp
import cvxpy as cp
import numpy as np
import clarabel
import mosek
import osqp

ZERO_CONE = "ZeroConeT"
NONNEGATIVE_CONE = "NonnegativeConeT"

def handle_cones(cones):
    m = 0
    cone_infos = []
    for cone in cones:
        name = str(cone)
        m += cone.dim
        if name == ZERO_CONE + f"({cone.dim})":
            cone_infos.append((cone.dim, ZERO_CONE)) 
        elif name == NONNEGATIVE_CONE + f"({cone.dim})":
            cone_infos.append((cone.dim, NONNEGATIVE_CONE))
        else:
            raise Exception(f"{cone} not supported!")
    return m, cone_infos

def with_cvxpy(n, P, q, D, b, cones, verbose):
    y = cp.Variable(n)
    m, cone_infos = handle_cones(cones) 
    s = cp.Variable(m)
    objective = 0.5 * cp.quad_form(y, cp.psd_wrap(P)) + q @ y
    constraints = [D @ y + s == b]
    for (dim, cone) in cone_infos:
        for i in range(dim):
            if cone == ZERO_CONE:
                constraints += [s[i] == 0]
            elif cone == NONNEGATIVE_CONE:
                constraints += [s[i] >= 0]
    problem = cp.Problem(cp.Minimize(objective), constraints)

    optimal_value = problem.solve(verbose=verbose)
    optimal_solution = y.value
    primal_slacks = s.value
    dual_solution = constraints[0].dual_value
    solve_time = problem.solver_stats.solve_time
    status = problem.status
    return (optimal_value, optimal_solution, primal_slacks,
            dual_solution, solve_time, status)

def with_clarabel(n, P, q, D, b, cones, verbose):
    settings = clarabel.DefaultSettings()
    settings.verbose = verbose
    problem = clarabel.DefaultSolver(P, q, D, b, cones, settings)
    solution = problem.solve()
    
    optimal_value = solution.obj_val
    optimal_solution = solution.x
    primal_slacks = solution.s
    dual_solution = solution.z
    solve_time = solution.solve_time
    status = solution.status
    return (optimal_value, optimal_solution, primal_slacks,
            dual_solution, solve_time, status)

def with_gurobi(n, P, q, D, b, cones, verbose):
    env = gp.Env(empty=True)
    env.setParam("OutputFlag", int(verbose))
    env.start()
    model = gp.Model("qp", env)
    y = model.addMVar(shape=n, lb=-gp.GRB.INFINITY, ub=gp.GRB.INFINITY)
    m, cone_infos = handle_cones(cones) 
    s = model.addMVar(shape=m, lb=-gp.GRB.INFINITY, ub=gp.GRB.INFINITY)
    objective = 0.5 * y @ P @ y + q @ y
    model.setObjective(objective)
    constraint = model.addConstr(D @ y + s == b)
    for (dim, cone) in cone_infos:
        for i in range(dim):
            if cone == ZERO_CONE:
                model.addConstr(s[i] == 0)
            elif cone == NONNEGATIVE_CONE:
                model.addConstr(s[i] >= 0)
    model.optimize()

    optimal_value = model.ObjVal
    optimal_solution = y.X
    primal_slacks = s.X
    dual_solution = -constraint.Pi
    solve_time = model.Runtime
    status = model.Status
    return (optimal_value, optimal_solution, primal_slacks,
            dual_solution, solve_time, status)

def with_mosek(n, P, q, D, b, cones, verbose):
    env = mosek.Env()
    task = env.Task()
    task.putintparam(mosek.iparam.log, int(verbose))
    m, cone_infos = handle_cones(cones)
    task.appendcons(m)
    task.appendvars(n + m)
    for j in range(n):
        task.putcj(j, q[j])
        task.putvarbound(j, mosek.boundkey.fr, -np.inf, np.inf)
    P = sparse.tril(P, format="coo")
    task.putqobj(P.row, P.col, P.data)
    stacked_D = sparse.hstack([D, sparse.identity(m)])
    task.putaijlist(*sparse.find(stacked_D))
    for j in range(m):
        task.putconbound(j, mosek.boundkey.fx, b[j], b[j])
    for (dim, cone) in cone_infos:
        for i in range(n, n + dim):
            if cone == ZERO_CONE:
                task.putvarbound(i, mosek.boundkey.fx, 0, 0)
            elif cone == NONNEGATIVE_CONE:
                task.putvarbound(i, mosek.boundkey.lo, 0, np.inf)
    task.putobjsense(mosek.objsense.minimize)
    task.optimize()

    optimal_value = task.getprimalobj(mosek.soltype.itr)
    primal_variables = np.array(task.getxx(mosek.soltype.itr))
    optimal_solution = primal_variables[:n]
    primal_slacks = primal_variables[n:]
    dual_solution = -np.array(task.gety(mosek.soltype.itr)[:m])
    solve_time = task.getdouinf(mosek.dinfitem.optimizer_time)
    status = task.getsolsta(mosek.soltype.itr)
    return (optimal_value, optimal_solution, primal_slacks,
            dual_solution, solve_time, status)

def with_osqp(n, P, q, D, b, cones, verbose):
    m, cone_infos = handle_cones(cones)
    stacked_P = sparse.block_diag([P, np.zeros((m, m))], format="csc")
    stacked_q = np.hstack([q, np.zeros(m)])
    stacked_D = sparse.vstack([
        sparse.hstack([D, sparse.identity(m)]),
        sparse.hstack([np.zeros((m, n)), sparse.identity(m)])], format="csc")
    cone_lb = []
    cone_ub = []
    for (dim, cone) in cone_infos:
        for _ in range(dim):
            if cone == ZERO_CONE:
                cone_lb.append(0)
                cone_ub.append(0)
            elif cone == NONNEGATIVE_CONE:
                cone_lb.append(0)
                cone_ub.append(np.inf)
    lb = np.hstack([b, cone_lb])
    ub = np.hstack([b, cone_ub])
    problem = osqp.OSQP()
    problem.setup(stacked_P, stacked_q, stacked_D, lb, ub, verbose=verbose)
    result = problem.solve()

    optimal_value = result.info.obj_val
    optimal_solution = result.x[:n]
    primal_slacks = result.x[n:]
    dual_solution = result.y[:m]
    solve_time = result.info.run_time
    status = result.info.status
    return (optimal_value, optimal_solution, primal_slacks,
            dual_solution, solve_time, status)