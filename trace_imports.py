print('Starting')
print('Importing supervisor')
from src.graph.supervisor import supervisor_node
print('Importing rag_worker')
from src.agents.rag_worker import rag_worker_node
print('Importing web_worker')
from src.agents.web_worker import web_worker_node
print('Importing utility_worker')
from src.agents.utility_worker import utility_worker_node
print('Importing scraper_worker')
from src.agents.scraper_worker import scraper_worker_node
print('Importing critic_worker')
from src.agents.critic_worker import critic_worker_node
print('Importing report_worker')
from src.agents.report_worker import report_worker_node
print('Importing frontend_worker')
from src.agents.frontend_worker import frontend_worker_node
print('Importing backend_worker')
from src.agents.backend_worker import backend_worker_node
print('Importing code_critic_worker')
from src.agents.code_critic_worker import code_critic_worker_node
print('Importing architect_worker')
from src.agents.architect_worker import architect_worker_node
print('Importing synthesizer')
from src.agents.synthesizer import synthesizer_node
print('Done!')
