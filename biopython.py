from Bio.PDB import PDBParser, Selection, NeighborSearch
from Bio.PDB.vectors import calc_angle
import numpy as np
import pandas as pd
import time
import pymol
import mdtraj as md


class Nodes:
    def __init__(self, name_=None,file_=False):
        self.name= name_
        self.parser= PDBParser(PERMISSIVE=1)
        self.structure= self.parser.get_structure(name_, file_)
        self.ns= NeighborSearch(list(self.structure.get_atoms()))
        #mdtraj
        self.pdb = md.load_pdb(file_)
        self.dssp_md = md.compute_dssp(self.pdb, simplified=False)
        
        self.model= self.structure[0]
        #self.dssp = DSSP(self.model, './Codes/3og7.pdb', file_type='PDB', dssp='dssp')
        self.all_dssps= []
        self.nodes_id, self.chains, self.positions, self.residues = [], [], [], []
        #Degrees não está com uma precisão boa, é preciso saber como pode ser feito igual o do RINGs
        self.degrees= []
        self.cut_dist= 8.0 # definir um limite de distância de corte (escolhido com base na literatura)
        #B-Factor, coords and filenames
        self.bfactors, self.coords, self.pdb_filename =[], [], []
        self.models= []
        
    
    def dssp_test(self):
        self.search_nodes()
        for residue in self.dssp:
            print(residue)
    
    def search_nodes(self):
        for model in self.structure:
            for chain in model:
                for residue in chain:
                    if str(residue.resname) != 'HOH': # ignore solvent
                        # Node_ID, Chain, Position and Residue
                        self.nodes_id.append(f"{chain.id}:{str(residue.id[1])}:_:{str(residue.resname)}")
                        self.chains.append(str(chain.id))
                        self.positions.append(residue.id[1])
                        if str(residue.resname) == '032':
                            #Se o resíduo for o 032 então ele não terá um Bfactor-CA nem coordenadas
                            self.bfactors.append('NaN')
                            self.coords.append(np.array(['NaN', 'NaN', 'NaN']))
                        self.residues.append(str(residue.resname))
                        
                        #Degree -> número de residuos diretamente conectados

                        degree= 0
                        
                        if 'CA' in residue:
                            #R ->  list of residues list of modules
                            for residue_2 in Selection.unfold_entities(model, 'R'):
                                if ( residue_2.get_id()[1] != residue.get_id()[1] ):
                                    #CA -> Carbono Alfa (mais preciso que outros átomos)
                                    #Calcular a distancia euclidiana das coordenadas desse carbono alfa
                                    if 'CA' in residue_2:
                                        distance= np.linalg.norm(residue["CA"].coord - residue_2["CA"].coord)
                                        if ( distance < self.cut_dist ):
                                            degree += 1 
                            
                        self.degrees.append(degree)

                        #Bfactor_CA
                        b_factor=0
                        count=0
                        for atom in residue:
                            if ( atom.get_name() == 'CA' ):
                                b_factor += atom.get_bfactor()
                                count += 1

                                coords= atom.get_coord()
                                self.coords.append(coords)
                                
                        if (count != 0):
                            bf_average= b_factor/count
                            self.bfactors.append(f"{bf_average:.3f}")
                        
                        #pdb filenames

                        self.pdb_filename.append(f"input_file.cif#{str(residue.id[1])}.{str(chain.id)}")
                        self.models.append(model.id + 1)

        # Pegando o DSSP 
        for i in range(len(self.dssp_md[0])):
            if i>0:
                if self.dssp_md[0][i] == 'NA':
                    pass
                else:
                    self.all_dssps.append(self.dssp_md[0][i] if self.dssp_md[0][i] != 'C' else '\t')
            else:
                
                self.all_dssps.append(self.dssp_md[0][i] if self.dssp_md[0][i] not in ['C', 'NA'] else '\t')  

    def print_output(self):
        self.search_nodes()
        for n in range(len(self.nodes_id)):
            try:
                print(f"{self.nodes_id[n]}\t{self.chains[n]}\t\t{self.positions[n]}\t\t{self.residues[n]}\t{self.all_dssps[n]}\t" +
                        f"{self.degrees[n]}\t{self.bfactors[n]:.3f}\t{self.coords[n][0]:.3f}\t{self.coords[n][1]:.3f}\t{self.coords[n][2]:.3f}\t" +
                        f"{self.pdb_filename[n]}\t{self.models[n]}"
                )
            except Exception as e:
                print(f"{self.nodes_id[n]}\t{self.chains[n]}\t\t{self.positions[n]}\t\t{self.residues[n]}\t{self.all_dssps[n]}\t" +
                        f"{self.degrees[n]}\t{self.bfactors[n]}\t{self.coords[n][0]}\t{self.coords[n][1]}\t{self.coords[n][2]}\t" +
                        f"{self.pdb_filename[n]}\t{self.models[n]}"
                )

    def to_file(self):
        self.search_nodes()

        colunas= ["NodeId", "Chain","Position",	"Residue",	"Dssp",	"Degree", "Bfactor_CA", "x", "y", "z", "pdbFileName", "Model"]
        
        x, y, z = [], [], []
        for coord in self.coords:
            if coord[0] != 'NaN':
                x.append(f"{coord[0]:.3f}")
                y.append(f"{coord[1]:.3f}")
                z.append(f"{coord[2]:.3f}")
            else:
                x.append(coord[0])
                y.append(coord[1])
                z.append(coord[2])

        data= pd.DataFrame(list(zip(self.nodes_id, self.chains, self.positions, self.residues, 
                                    self.all_dssps, self.degrees, self.bfactors, x, y, z, self.pdb_filename, self.models
        )), columns= colunas)
        
        data.to_csv(f'./{self.name}_nodes.csv', sep='\t', index=False)
 



class Edges(Nodes):
    def __init__(self, name, file_pdb, multiple=False):
        Nodes.__init__(self ,name_=name, file_= file_pdb)
        self.edges = []
        self.res= [res for res in self.structure.get_residues()]
        self.mc = ['O', 'N']
        self.lighbdonor = {'ARG': ['NE', 'NH1', 'NH2'], 
                            'ASN':['ND2'], 
                            'HIS': ['NE2', 'ND1'], 
                            'SER': ['OG'], 
                            'TYR': ['OH'], 
                            'CYS': ['SG'],
                            'THR': ['OG1'], 
                            'GLN': ['NE2'], 
                            'LYS': ['NZ'], 
                            'TRP': ['NE1']
                            }
        self.lighbac= {'ASN': ['OD1'], 
                        'GLN': ['OE1'],
                         'MET': ['SD'], 
                         'ASP': ['OD1', 'OD2'], 
                         'GLU': ['OE1', 'OE2'], 
                         'SER': ['OG'], 
                         'THR': ['OG1'], 
                         'HIS': ['ND1'], 
                         'TYR': ['OH']
                         }
        self.ligvdw = ['C','CB', 'CG1', 'CG2', 'CD1', 'CD2', 'CE']
        self.ligpipi = ['HIS', 'TYR', 'TRP', 'PHE']
        self.nodes_id1, self.nodes_id2, self.bonds= [], [], []
        self.distances, self.donors, self.angles= [], [], []
        self.atom1, self.atom2 = [], []
        self.bonds_check = []
        self.analyzed_pairs = set()
        self.energies = [] 
        self.multiple= multiple
        self.ligands = {'hb': 0, 'vdw': 0, "ionic": 0}
        

    def Iac(self):

        # Eles não calculam mais essas ligações na nova versão 

        lig_032 = []
        for residue in self.structure.get_residues():
            if str(residue.resname) == "032":
                lig_032.append(residue)
        
        for residue in lig_032:
            for atom in residue:
                for neighbor_pair in self.ns.search(atom.coord, 6.5, level= 'R'):
                    for atom2 in neighbor_pair:
                        if atom2.get_name() == 'CA':
                            distance = np.linalg.norm(atom.coord - atom2.coord)
                            #verificando se o átomo vizinho é de outro resíduo
                            if neighbor_pair != residue:
                                print(residue.resname, neighbor_pair.resname, neighbor_pair.id[1], distance)
    
    def search_H(self):
        for atom in self.structure.get_atoms():
            if atom.fullname[1] == 'H':
                print(atom)
    
    def Bonds(self):
        chain1= ''
        chain2= ''
        vdw_radii = {'C': 1.77, 'S': 1.89, 'N': 1.8, 'O': 1.4}
        is_vdw = False
        global n_or_o_donor
        global ionic_donor
        lower_dist = 100
        
        # verificar se o par já foi analisado
        
        #achar como calcular o angulo entre os átomos
        for chain in self.structure.get_chains():
            for residue in chain:
                
                if residue.resname in ['032', 'HOH']:
                    continue
                for atom in residue:
                    atom_name= atom.get_name()
                    is_vdw = False

                    # Looking for HBOND
                    if atom.fullname[1] in ['N', 'O'] or (atom_name == 'SG' and residue.resname == 'CYS'):
                        neighbors= self.ns.search(atom.coord, 5.5)
                        for neighbor in neighbors:
                            
                            neig_name= neighbor.get_name()
                            neig_res= neighbor.get_parent()
                            if neig_res.resname in ['HOH', '032']:
                                continue 
                            if neig_res.id[1] == residue.id[1] or neig_name[0] == atom_name[0]:
                                continue

                            pair = (int(residue.id[1]), int(neig_res.id[1]))

                            if pair in self.analyzed_pairs:
                                continue
                            else:
                                self.analyzed_pairs.add((int(neig_res.id[1]), int(residue.id[1])))


                            if neighbor.fullname[1] in ['N', 'O'] or (neighbor.get_name() == 'SG' and neig_res.resname == 'CYS'):
                                distance= np.linalg.norm(atom.coord - neighbor.coord)
                                #Verificando quem é doador
                                if (atom_name[0] == 'N' or (atom_name in ['OG', 'OH', 'OG1', 'SG'] and residue.resname in list(self.lighbdonor.keys()))) and (neig_name[0] == 'O' or (neig_name in ['SD', 'ND1'] and neig_res.resname in list(self.lighbac.keys()))):
                                    # Aqui o doador vai ser o atomo principal
                                    n_or_o_donor = atom

                                    h_list = [a for a in residue if a.element == 'H']
                                    h_distances= {}
                                    for h_atom in h_list:
                                        h_dist = np.linalg.norm(atom.coord - h_atom.coord)
                                        h_distances[h_dist] = h_atom
                                    min_h = min(list(h_distances.keys()))
                                    h_donor = h_distances[min_h]
                                    

                                elif (neig_name[0] == 'N' or (neig_name in ['OG', 'OH', 'OG1', 'SG'] and neig_res.resname in list(self.lighbdonor.keys()))) and (atom_name[0] == 'O' or (atom_name in ['SD', 'ND1'] and residue.resname in list(self.lighbac.keys()))):
                                    # Aqui o doador vai ser o atomo vizinho
                                    n_or_o_donor = neighbor

                                    h_list = [a for a in neig_res if a.element == 'H']

                                    h_distances= {}
                                    for h_atom in h_list:
                                        h_dist = np.linalg.norm(neighbor.coord - h_atom.coord)
                                        h_distances[h_dist] = h_atom
                                    min_h = min(list(h_distances.keys()))
                                    h_donor = h_distances[min_h]
                                    
                                terceiro_vetor= h_donor.get_vector()
                                neighbor_vector= neighbor.get_vector()
                                a_vector = atom.get_vector()

                                angle = 0.0
                                if n_or_o_donor == atom:
                                    angle = np.degrees(calc_angle(terceiro_vetor,a_vector, neighbor_vector))
                                else:
                                    angle = np.degrees(calc_angle(terceiro_vetor, neighbor_vector, a_vector))

                                if 2.5 < distance <= 3.5 and angle <= 63.0:
                                    
                                    #Verificando se é a cadeia principal ou lateral 
                                    if atom.name in ["N", "O"]:
                                        chain1 = 'MC'
                                    else:
                                        chain1 = 'SC'
                                    
                                    if neighbor.name in ['N', 'O']:
                                        chain2 = 'MC'
                                    else:
                                        chain2 = 'SC'
                                    
                                    if self.multiple:
                                        self.bonds_check.append((f"{chain.id}:{str(residue.id[1])}:_:{str(residue.resname)}", 
                                                         f"{chain.id}:{str(neig_res.id[1])}:_:{str(neig_res.resname)}"))
                                    
                                    self.nodes_id1.append(f"{chain.id}:{str(residue.id[1])}:_:{str(residue.resname)}")
                                    self.nodes_id2.append(f"{chain.id}:{str(neig_res.id[1])}:_:{str(neig_res.resname)}")
                                    self.bonds.append(f"HBOND:{chain1}_{chain2}")
                                    self.distances.append(f"{distance:.3f}")
                                    self.angles.append(f"{angle:.3f}")
                                    if distance <= 1.5:
                                        self.energies.append(f"{115.000:.3f}")
                                    elif distance >= 2.2:
                                        self.energies.append(f"{17.000:.3f}")
                                    else:
                                        self.energies.append(f"{40.000:.3f}")
                                    self.atom1.append(atom_name)
                                    self.atom2.append(neig_name)
                                    self.donors.append(f"{chain.id}:{str(n_or_o_donor.get_parent().id[1])}:_:{str(n_or_o_donor.get_parent().resname)}")
                                    self.ligands["hb"] += 1

                    #Looking for VDW
                    elif atom.fullname[1] in ['C', 'S', 'O', 'N']:
                        neighbors= self.ns.search(atom.coord,3.9)
                        for neighbor in neighbors:
                            is_vdw = False

                            neig_name= neighbor.get_name()
                            neig_res= neighbor.get_parent()
                            distance= np.linalg.norm(atom.coord - neighbor.coord)
                            if neig_res.id[1] == residue.id[1] or neig_name in ["CA", "CH2"] or atom_name in ["CA", "CH2"]  or (atom_name=='C' and neig_name=='C'):
                                continue

                            if neig_res.resname in ['HOH', '032']:
                                continue

                            pair = (int(residue.id[1]), int(neig_res.id[1]))
                            
                            if pair in self.analyzed_pairs:
                                continue
                            else:
                                self.analyzed_pairs.add((int(neig_res.id[1]), int(residue.id[1])))

                            if neighbor.fullname[1] in ['C', 'S', 'O', 'N'] :
                                
                                if atom.name in ["C", "S"]:
                                    chain1 = 'MC'
                                else:
                                    chain1 = 'SC'
                                
                                if neighbor.name in ['C', 'S']:
                                    chain2 = 'MC'
                                else:
                                    chain2 = 'SC'

                                if (atom.fullname[1] == "C" and neighbor.fullname[1]  == "C") or (atom.fullname[1]  == "C" and neighbor.fullname[1]  == "S") or (atom.fullname[1]  == "S" and neighbor.fullname[1]  == "C"):
                                    is_vdw = True
                            
                                elif (atom_name[0] == "N" or atom_name[0] == "O" ) and neig_name[0] == "C":
                                    if (residue.resname == 'GLN' and (atom_name == "OE1" or atom_name == "NE2")) or (
                                        residue.resname == 'ASN' and (atom_name == "OD1" or atom_name == "ND2")):
                                        
                                        is_vdw = True
                                        
                                elif (neig_name[0] == "N" or neig_name[0] == "O" ) and atom_name[0] == "C":
                                    if (neig_res.resname == 'GLN' and (neighbor.name == "OE1" or neighbor.name == "NE2")) or (
                                        neig_res.resname == 'ASN' and (neighbor.name == "OD1" or neighbor.name == "ND2")):
                                        
                                            is_vdw = True
                                        
                            if is_vdw:
                                check_dist= distance - vdw_radii[atom.name[0]] - vdw_radii[neighbor.name[0]]
                                    
                                if check_dist <= 0.5:
                                    if self.multiple:
                                        self.bonds_check.append((f"{chain.id}:{str(residue.id[1])}:_:{str(residue.resname)}", 
                                                         f"{chain.id}:{str(neig_res.id[1])}:_:{str(neig_res.resname)}"))
                        
                                    self.nodes_id1.append(f"{chain.id}:{str(residue.id[1])}:_:{str(residue.resname)}")
                                    self.nodes_id2.append(f"{chain.id}:{str(neig_res.id[1])}:_:{str(neig_res.resname)}")
                                    self.donors.append("NaN")
                                    self.angles.append("NaN")
                                    self.energies.append(f"{6.000:.3f}")
                                    self.bonds.append(f"VDW:{chain1}_{chain2}")
                                    self.distances.append(f"{distance:.3f}")
                                    self.atom1.append(atom_name)
                                    self.atom2.append(neig_name)
                                    self.ligands["vdw"] += 1

                    # Looking for SBOND
                    if atom_name[0] == 'S':
                        neighbors= self.ns.search(atom.coord, 3.5)
                        for neighbor in neighbors:
                            neig_res = neighbor.get_parent()

                            if neig_res.id[1] == residue.id[1]:
                                continue
                            if pair in self.analyzed_pairs:
                                continue
                            else:
                                self.analyzed_pairs.add((int(neig_res.id[1]), int(residue.id[1])))
                                    
                            neig_name= neighbor.get_name()
                            neig_res= neighbor.get_parent()
                            distance= np.linalg.norm(atom.coord - neighbor.coord)
                            if neig_name[0] == 'S' and distance<=2.5:
                                self.nodes_id1.append(f"{chain.id}:{str(residue.id[1])}:_:{str(residue.resname)}")
                                self.nodes_id2.append(f"{chain.id}:{str(neig_res.id[1])}:_:{str(neig_res.resname)}")
                                self.donors.append("NaN")
                                self.angles.append("NaN")
                                self.energies.append(f"{167.000:.3f}")
                                self.bonds.append(f"SBOND:{chain1}_{chain2}")
                                self.distances.append(f"{distance:.3f}")
                                self.atom1.append(atom_name)
                                self.atom2.append(neig_name)
                    # Salt Bridges
                    
                    if residue.resname in ['ARG', 'LYS', 'HIS', 'ASP', 'GLU']:
                        analyzed_ionic= set()
                        neighbors= self.ns.search(atom.coord, 8)
                        for neighbor in neighbors:
                            neig_res= neighbor.get_parent()
                            neig_name= neighbor.get_name()
                            if neig_res.id[1] == residue.id[1]:
                                continue
                            if atom_name in ['CZ', 'NZ'] or neig_res in ['CZ', 'NZ']:
                                pair = (int(residue.id[1]), int(neig_res.id[1]))
                                
                                if pair in self.analyzed_pairs or pair in analyzed_ionic:
                                    continue
                                else:
                                    self.analyzed_pairs.add((int(neig_res.id[1]), int(residue.id[1])))
                                    analyzed_ionic.add(pair)

                                if neig_res.resname in ['ARG', 'LYS', 'HIS', 'ASP', 'GLU']:
                                    
                                    if residue.resname in ['ARG', 'LYS', 'HIS'] and neig_res.resname in ['ASP', 'GLU']:
                                        # aqui o átomo vai ser o doador 
                                        ionic_donor= atom

                                    elif neig_res.resname in ['ARG', 'LYS', 'HIS'] and residue.resname in ['ASP', 'GLU']:
                                        # aqui o neighbor vai ser o doador
                                        ionic_donor = neighbor
                                        
                                    chain1= 'MC' if len(atom_name)==1 else 'SC'
                                    chain2= 'MC' if len(neig_name)==1 else 'SC'
                                        
                                    distance = np.linalg.norm(atom.coord - neighbor.coord)
                                    # angle = np.degrees(calc_angle())
                                    
                                    if distance <= 4.0:
                                        if self.multiple:
                                            self.bonds_check.append((f"{chain.id}:{str(residue.id[1])}:_:{str(residue.resname)}", 
                                                         f"{chain.id}:{str(neig_res.id[1])}:_:{str(neig_res.resname)}"))
                                            #ionic_check.add(((residue.id[1], neig_res.id[1]),atom, neighbor, distance))
                                        
                                        self.nodes_id1.append(f"{chain.id}:{str(residue.id[1])}:_:{str(residue.resname)}")
                                        self.nodes_id2.append(f"{chain.id}:{str(neig_res.id[1])}:_:{str(neig_res.resname)}")
                                        self.bonds.append(f"IONIC:{chain1}_{chain2}")
                                        self.distances.append(f"{distance:.3f}")
                                        self.angles.append(f"NAN")
                                        self.energies.append(f"{20.000:.3f}")
                                        if atom_name in ['CZ', 'NZ']:
                                            self.atom1.append(atom_name)
                                            self.atom2.append(f"{neighbor.get_coord()[0]:.3f},{neighbor.get_coord()[1]:.3f},{neighbor.get_coord()[2]:.3f}")
                                        elif atom_name not in ['CZ', 'NZ'] and neig_name in ['CZ', 'NZ']:
                                            self.atom1.append(f"{atom.get_coord()[0]:.3f},{atom.get_coord()[1]:.3f},{atom.get_coord()[2]:.3f}")
                                            self.atom2.append(neig_name)

                                        self.donors.append(f"{chain.id}:{str(ionic_donor.get_parent().id[1])}:_:{str(ionic_donor.get_parent().resname)}")
                                        self.ligands["ionic"] += 1
                    
            #check the multiple interactions 
    def analyse(self, bond, lig):
        for pair in self.bonds_check:
            pair_dist, pair_idx = [], []
            
            for line in range(len(self.nodes_id1)):
                
                if (pair == (self.nodes_id1[line], self.nodes_id2[line]) and (bond in self.bonds[line])):
                    pair_dist.append(self.distances[line])
                    pair_idx.append(line)
            
            if len(pair_dist) > 1:
                min_idx = np.argmin(pair_dist)
                min_pair = pair_idx[min_idx]
                for i in pair_idx:
                    if i != min_pair:
                        self.nodes_id1.pop(i)
                        self.nodes_id2.pop(i)
                        self.donors.pop(i)
                        self.angles.pop(i)
                        self.energies.pop(i)
                        self.bonds.pop(i)
                        self.distances.pop(i)
                        self.atom1.pop(i)
                        self.atom2.pop(i)
                        self.ligands[lig] -= 1
    
    def multiple_mode(self):
        bonds = [("HBOND", "hb"), ("VDW", "vdw")]
        for b in bonds:
            self.analyse(b[0], b[1])
        
    def to_file(self):
        self.Bonds()
        if self.multiple:
            self.multiple_mode()
        colunas= ["NodeId1", "Interaction"	,"NodeId2",	"Distance",	"Angle","Energy", "Atom1", "Atom2", "Donor"]

        data= pd.DataFrame(list(zip(self.nodes_id1, self.bonds, self.nodes_id2, self.distances, 
                                    self.angles,self.energies, self.atom1, self.atom2, self.donors)), columns= colunas)
        
        data.to_csv(f'./{self.name}_edges.csv', sep='\t', index=False)
        
    def print_output(self):
        self.Bonds()

        if self.multiple:
            self.multiple_mode()

        print(len(self.nodes_id1), len(self.donors))
        time.sleep(2)
        for n in range(len(self.nodes_id1)):
            try:
                print(f"{self.nodes_id1[n]}\t{self.bonds[n]}\t{self.nodes_id2[n]}\t{self.distances[n]}\t{self.angles[n]}\t\t{self.energies[n]}\t\t{self.atom1[n]}\t{self.atom2[n]}\t{self.donors[n]}")
                
            except Exception as e:
                print(e)
                print(f"{self.nodes_id1[n]}\t{self.bonds[n]}\t{self.nodes_id2[n]}\t{self.distances[n]}\t{self.angles[n]}\t\t{self.energies[n]}\t\t{self.atom1[n]}\t{self.atom2[n]}\t{self.donors[n]}")
        print(self.ligands)


def run(name_= False, file= None):
    start= time.time()

    if file is None:
        raise Exception("Load File")

    # pymol.cmd.load(file, 'myprotein')
    # pymol.cmd.h_add()
    # pymol.cmd.save('./temp/input_file.pdb')
    # time.sleep(2)

    edges= Edges(name_, './temp/input_file.pdb', multiple= True)
    edges.print_output()
    

    print(f"---{(time.time() - start)} seconds ---")

run('3og7', './temp/3og7.pdb')

# Colocar um trycatch nas ligações com Hidrogenio 