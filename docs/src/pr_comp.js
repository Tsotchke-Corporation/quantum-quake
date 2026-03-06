// Ported from: WinQuake/pr_comp.h -- defs shared with qcc

// type definitions (C: typedef int func_t; typedef int string_t;)
// In JS these are just number values used as indices

// etype_t
export const ev_void = 0;
export const ev_string = 1;
export const ev_float = 2;
export const ev_vector = 3;
export const ev_entity = 4;
export const ev_field = 5;
export const ev_function = 6;
export const ev_pointer = 7;

// global offsets for parameter passing
export const OFS_NULL = 0;
export const OFS_RETURN = 1;
export const OFS_PARM0 = 4; // leave 3 ofs for each parm to hold vectors
export const OFS_PARM1 = 7;
export const OFS_PARM2 = 10;
export const OFS_PARM3 = 13;
export const OFS_PARM4 = 16;
export const OFS_PARM5 = 19;
export const OFS_PARM6 = 22;
export const OFS_PARM7 = 25;
export const RESERVED_OFS = 28;

// opcodes
export const OP_DONE = 0;
export const OP_MUL_F = 1;
export const OP_MUL_V = 2;
export const OP_MUL_FV = 3;
export const OP_MUL_VF = 4;
export const OP_DIV_F = 5;
export const OP_ADD_F = 6;
export const OP_ADD_V = 7;
export const OP_SUB_F = 8;
export const OP_SUB_V = 9;

export const OP_EQ_F = 10;
export const OP_EQ_V = 11;
export const OP_EQ_S = 12;
export const OP_EQ_E = 13;
export const OP_EQ_FNC = 14;

export const OP_NE_F = 15;
export const OP_NE_V = 16;
export const OP_NE_S = 17;
export const OP_NE_E = 18;
export const OP_NE_FNC = 19;

export const OP_LE = 20;
export const OP_GE = 21;
export const OP_LT = 22;
export const OP_GT = 23;

export const OP_LOAD_F = 24;
export const OP_LOAD_V = 25;
export const OP_LOAD_S = 26;
export const OP_LOAD_ENT = 27;
export const OP_LOAD_FLD = 28;
export const OP_LOAD_FNC = 29;

export const OP_ADDRESS = 30;

export const OP_STORE_F = 31;
export const OP_STORE_V = 32;
export const OP_STORE_S = 33;
export const OP_STORE_ENT = 34;
export const OP_STORE_FLD = 35;
export const OP_STORE_FNC = 36;

export const OP_STOREP_F = 37;
export const OP_STOREP_V = 38;
export const OP_STOREP_S = 39;
export const OP_STOREP_ENT = 40;
export const OP_STOREP_FLD = 41;
export const OP_STOREP_FNC = 42;

export const OP_RETURN = 43;
export const OP_NOT_F = 44;
export const OP_NOT_V = 45;
export const OP_NOT_S = 46;
export const OP_NOT_ENT = 47;
export const OP_NOT_FNC = 48;
export const OP_IF = 49;
export const OP_IFNOT = 50;
export const OP_CALL0 = 51;
export const OP_CALL1 = 52;
export const OP_CALL2 = 53;
export const OP_CALL3 = 54;
export const OP_CALL4 = 55;
export const OP_CALL5 = 56;
export const OP_CALL6 = 57;
export const OP_CALL7 = 58;
export const OP_CALL8 = 59;
export const OP_STATE = 60;
export const OP_GOTO = 61;
export const OP_AND = 62;
export const OP_OR = 63;

export const OP_BITAND = 64;
export const OP_BITOR = 65;

// dstatement_t - bytecode statement
export class dstatement_t {

	constructor() {

		this.op = 0; // unsigned short
		this.a = 0; // short
		this.b = 0; // short
		this.c = 0; // short

	}

}

// DEF_SAVEGLOBAL flag
export const DEF_SAVEGLOBAL = ( 1 << 15 );

// ddef_t - definition of a global or field
export class ddef_t {

	constructor() {

		this.type = 0; // unsigned short - if DEF_SAVEGLOBAL bit is set, needs saving
		this.ofs = 0; // unsigned short
		this.s_name = 0; // int - offset into pr_strings

	}

}

export const MAX_PARMS = 8;

// dfunction_t - QuakeC function definition
export class dfunction_t {

	constructor() {

		this.first_statement = 0; // int - negative numbers are builtins
		this.parm_start = 0; // int
		this.locals = 0; // int - total ints of parms + locals

		this.profile = 0; // int - runtime profiling

		this.s_name = 0; // int - offset into pr_strings
		this.s_file = 0; // int - source file defined in

		this.numparms = 0; // int
		this.parm_size = new Uint8Array( MAX_PARMS ); // byte[8]

	}

}

export const PROG_VERSION = 6;

// dprograms_t - progs.dat file header
export class dprograms_t {

	constructor() {

		this.version = 0;
		this.crc = 0; // check of header file

		this.ofs_statements = 0;
		this.numstatements = 0; // statement 0 is an error

		this.ofs_globaldefs = 0;
		this.numglobaldefs = 0;

		this.ofs_fielddefs = 0;
		this.numfielddefs = 0;

		this.ofs_functions = 0;
		this.numfunctions = 0; // function 0 is an empty

		this.ofs_strings = 0;
		this.numstrings = 0; // first string is a null string

		this.ofs_globals = 0;
		this.numglobals = 0;

		this.entityfields = 0;

	}

}
